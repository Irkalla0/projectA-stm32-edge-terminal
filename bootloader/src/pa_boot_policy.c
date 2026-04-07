#include "pa_boot_policy.h"

pa_boot_decision_t pa_boot_decide(const pa_boot_state_t *state, uint8_t max_attempts)
{
  if (state == 0)
    return PA_BOOT_DECISION_STAY_LOADER;
  if (state->state_version != PA_STATE_VERSION)
    return PA_BOOT_DECISION_STAY_LOADER;

  if (state->active_slot != PA_SLOT_A && state->active_slot != PA_SLOT_B)
    return PA_BOOT_DECISION_STAY_LOADER;

  if (state->pending_slot == PA_SLOT_A || state->pending_slot == PA_SLOT_B)
  {
    if (max_attempts == 0U)
      return PA_BOOT_DECISION_STAY_LOADER;
    if (state->boot_attempts >= max_attempts)
      return PA_BOOT_DECISION_BOOT_ACTIVE;
    return PA_BOOT_DECISION_BOOT_PENDING;
  }

  return PA_BOOT_DECISION_BOOT_ACTIVE;
}

void pa_boot_state_init(pa_boot_state_t *state)
{
  if (state == 0)
    return;
  state->magic_u32 = PA_STATE_MAGIC_U32;
  state->state_version = PA_STATE_VERSION;
  state->active_slot = PA_SLOT_A;
  state->pending_slot = PA_SLOT_NONE;
  state->boot_attempts = 0U;
  state->last_result = PA_LAST_RESULT_UNKNOWN;
  state->seq = 0U;
  state->slot_a_size = 0U;
  state->slot_a_crc32 = 0U;
  state->slot_b_size = 0U;
  state->slot_b_crc32 = 0U;
  /* CRC and reserved are managed by storage layer. */
}

void pa_boot_set_slot_meta(pa_boot_state_t *state, uint8_t slot, uint32_t size, uint32_t crc32)
{
  if (state == 0)
    return;
  if (slot == PA_SLOT_A)
  {
    state->slot_a_size = size;
    state->slot_a_crc32 = crc32;
  }
  else if (slot == PA_SLOT_B)
  {
    state->slot_b_size = size;
    state->slot_b_crc32 = crc32;
  }
}

void pa_boot_mark_pending(pa_boot_state_t *state, uint8_t slot)
{
  if (state == 0)
    return;
  if (slot != PA_SLOT_A && slot != PA_SLOT_B)
    return;
  state->pending_slot = slot;
  state->boot_attempts = 0U;
  state->last_result = PA_LAST_RESULT_UNKNOWN;
  state->seq++;
}

void pa_boot_mark_confirm(pa_boot_state_t *state)
{
  if (state == 0)
    return;
  if (state->pending_slot == PA_SLOT_A || state->pending_slot == PA_SLOT_B)
    state->active_slot = state->pending_slot;
  state->pending_slot = PA_SLOT_NONE;
  state->boot_attempts = 0U;
  state->last_result = PA_LAST_RESULT_OK;
  state->seq++;
}

void pa_boot_mark_fail_once(pa_boot_state_t *state, uint8_t max_attempts)
{
  if (state == 0)
    return;
  if (state->pending_slot != PA_SLOT_A && state->pending_slot != PA_SLOT_B)
    return;

  if (state->boot_attempts < 0xFFU)
    state->boot_attempts++;
  state->seq++;

  if (max_attempts != 0U && state->boot_attempts >= max_attempts)
  {
    state->pending_slot = PA_SLOT_NONE;
    state->boot_attempts = 0U;
    state->last_result = PA_LAST_RESULT_ROLLBACK;
  }
}

void pa_boot_mark_abort(pa_boot_state_t *state)
{
  if (state == 0)
    return;
  if (state->pending_slot == PA_SLOT_A || state->pending_slot == PA_SLOT_B)
  {
    state->pending_slot = PA_SLOT_NONE;
    state->boot_attempts = 0U;
    state->last_result = PA_LAST_RESULT_ROLLBACK;
    state->seq++;
  }
}
