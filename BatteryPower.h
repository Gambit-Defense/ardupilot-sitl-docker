#pragma once

#include <math.h>
#include <stdint.h>
#include <string.h>

namespace HALSITL {

// Power state and actuator mapping for the built-in CONGO vehicle frames.
class BatteryPower {
public:
    // Update power from valid charge accounting; recharge at 0.1% restores power.
    void update(bool healthy, int32_t capacity_mah, float consumed_mah)
    {
        if (healthy && capacity_mah > 0 && isfinite(consumed_mah) && consumed_mah >= 0.f) {
            constexpr double minimum_charge_pct = 0.1;
            const double remaining_pct = (static_cast<double>(capacity_mah) - consumed_mah) * 100.0 / capacity_mah;
            _depleted = remaining_pct < minimum_charge_pct;
        }
    }

    // Suppress propulsion in the supported frames, preserving non-motor servos.
    bool apply(uint16_t *servos, const char *frame) const
    {
        if (!_depleted) {
            return false;
        }
        constexpr uint16_t minimum_pwm = 1000;
        constexpr uint16_t neutral_pwm = 1500;
        if (strcmp(frame, "+") == 0) {
            for (uint8_t i = 0; i < 4; i++) {
                servos[i] = minimum_pwm;
            }
        } else if (strcmp(frame, "plane") == 0) {
            servos[2] = minimum_pwm;
        } else if (strcmp(frame, "quadplane") == 0) {
            servos[2] = minimum_pwm;
            for (uint8_t i = 4; i < 8; i++) {
                servos[i] = minimum_pwm;
            }
        } else if (strcmp(frame, "rover") == 0) {
            servos[2] = neutral_pwm;
        } else {
            return false;
        }
        return true;
    }

private:
    bool _depleted = false;
};

} // namespace HALSITL
