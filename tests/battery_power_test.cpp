#include "BatteryPower.h"
#include <assert.h>
#include <limits>

// Check cutoff below 0.1% and recovery for every frame launched by entrypoint.sh.
static void check_frame(const char *frame, unsigned motor_mask, uint16_t off_pwm)
{
    HALSITL::BatteryPower power;
    uint16_t servos[16];
    for (auto &servo : servos) {
        servo = 1800;
    }
    power.update(true, 1000, 998.f);
    assert(!power.apply(servos, frame)); // 0.2%: a rounded display is not the cutoff.
    power.update(true, 1000, 999.f);
    assert(!power.apply(servos, frame)); // Exactly 0.1% is still powered.
    for (auto servo : servos) {
        assert(servo == 1800);
    }
    power.update(true, 1000, 999.5f); // 0.05%: cut off before exact zero.
    assert(power.apply(servos, frame));
    for (unsigned i = 0; i < 16; i++) {
        assert(servos[i] == ((motor_mask & (1U << i)) ? off_pwm : 1800));
    }
    // New commands remain suppressed while depleted.
    power.update(true, 1000, 1000.f);
    for (auto &servo : servos) {
        servo = 2000;
    }
    assert(power.apply(servos, frame));
    for (unsigned i = 0; i < 16; i++) {
        assert(servos[i] == ((motor_mask & (1U << i)) ? off_pwm : 2000));
    }
    // Restored charge at the threshold permits new commands without a restart.
    power.update(true, 1000, 999.f);
    for (auto &servo : servos) {
        servo = 1800;
    }
    assert(!power.apply(servos, frame));
    for (auto servo : servos) {
        assert(servo == 1800);
    }
    power.update(true, 1000, 1001.f);
    assert(power.apply(servos, frame));
    power.update(true, 1000, 0.f);
    assert(!power.apply(servos, frame));
}

// Invalid accounting must not change the last valid power state.
static void invalid_samples(HALSITL::BatteryPower &power)
{
    uint16_t servos[16] = {};
    const bool depleted = power.apply(servos, "+");
    // Check each invalid sample preserves the state that preceded it.
    const auto check = [&](bool healthy, int32_t capacity_mah, float consumed_mah) {
        power.update(healthy, capacity_mah, consumed_mah);
        assert(power.apply(servos, "+") == depleted);
    };
    check(false, 1000, 0.f);
    check(true, 0, 0.f);
    check(true, -1, 0.f);
    check(true, 1000, -1.f);
    check(true, 1000, std::numeric_limits<float>::quiet_NaN());
    check(true, 1000, std::numeric_limits<float>::infinity());
}

// Exercise supported propulsion mappings and invalid or missing battery accounting.
int main()
{
    check_frame("+", 0x0f, 1000);
    check_frame("plane", 1U << 2, 1000);
    check_frame("quadplane", 0xf0 | (1U << 2), 1000);
    check_frame("rover", 1U << 2, 1500);
    HALSITL::BatteryPower power;
    uint16_t servos[16] = {};
    power.update(false, 1000, 1000.f);
    invalid_samples(power);
    assert(!power.apply(servos, "+"));
    power.update(true, 1000, 1001.f);
    assert(power.apply(servos, "+"));
    invalid_samples(power);
    assert(power.apply(servos, "+"));
    // Unknown frames must not be assigned the wrong throttle neutral.
    servos[2] = 1750;
    assert(!power.apply(servos, "plane-revthrust"));
    assert(servos[2] == 1750);
    assert(!power.apply(servos, "rover-skid"));
    power.update(true, 10000, 9990.f); // Threshold scales with pack capacity.
    assert(!power.apply(servos, "+"));
    power.update(true, 10000, 9995.f);
    assert(power.apply(servos, "+"));
    HALSITL::BatteryPower restarted;
    assert(!restarted.apply(servos, "+"));
}
