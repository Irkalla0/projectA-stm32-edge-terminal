#include "../include/boot_cfg.h"
#include "../include/boot_storage.h"
#include "../include/boot_upgrade.h"
#include "../../bootloader/include/pa_boot_policy.h"

/*
 * Bootloader entry skeleton for Project A final architecture.
 * Board-specific startup, watchdog, peripheral init, and vector jump glue
 * should be integrated in production firmware project.
 */

static int jump_to_app(uint32_t app_base)
{
  (void)app_base;
  /* Porting hook: set MSP, remap VTOR, branch to reset handler */
  return 0;
}

int main(void)
{
  pa_boot_state_t state;
  pa_boot_decision_t decision;
  uint32_t target = APP_SLOT_A_BASE;

  if (boot_storage_read(&state) != 0)
  {
    pa_boot_state_init(&state);
    boot_storage_write(&state);
  }

  decision = pa_boot_decide(&state, BOOT_MAX_TRIAL_ATTEMPTS);
  if (decision == PA_BOOT_DECISION_BOOT_PENDING)
  {
    target = (state.pending_slot == PA_SLOT_B) ? APP_SLOT_B_BASE : APP_SLOT_A_BASE;
  }
  else if (decision == PA_BOOT_DECISION_BOOT_ACTIVE)
  {
    target = (state.active_slot == PA_SLOT_B) ? APP_SLOT_B_BASE : APP_SLOT_A_BASE;
  }
  else
  {
    /* stay in loader mode waiting for upgrade */
    for (;;)
    {
    }
  }

  if (jump_to_app(target) != 0)
  {
    for (;;)
    {
    }
  }

  return 0;
}
