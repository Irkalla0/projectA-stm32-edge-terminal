#ifndef PA_BOOT_POLICY_H
#define PA_BOOT_POLICY_H

#include <stdint.h>
#include "pa_boot_protocol.h"

#ifdef __cplusplus
extern "C" {
#endif

typedef enum
{
  PA_BOOT_DECISION_BOOT_ACTIVE = 0,
  PA_BOOT_DECISION_BOOT_PENDING = 1,
  PA_BOOT_DECISION_STAY_LOADER = 2
} pa_boot_decision_t;

/* Read-only decision used at reset time. */
pa_boot_decision_t pa_boot_decide(const pa_boot_state_t *state, uint8_t max_attempts);

/* State mutation helpers used by upgrader/bootloader flow. */
void pa_boot_state_init(pa_boot_state_t *state);
void pa_boot_set_slot_meta(pa_boot_state_t *state, uint8_t slot, uint32_t size, uint32_t crc32);
void pa_boot_mark_pending(pa_boot_state_t *state, uint8_t slot);
void pa_boot_mark_confirm(pa_boot_state_t *state);
void pa_boot_mark_fail_once(pa_boot_state_t *state, uint8_t max_attempts);
void pa_boot_mark_abort(pa_boot_state_t *state);

#ifdef __cplusplus
}
#endif

#endif /* PA_BOOT_POLICY_H */

