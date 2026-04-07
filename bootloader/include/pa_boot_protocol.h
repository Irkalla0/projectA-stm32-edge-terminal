#ifndef PA_BOOT_PROTOCOL_H
#define PA_BOOT_PROTOCOL_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define PA_IMG_MAGIC_U32 0x57464150UL /* "PAFW" little-endian */
#define PA_STATE_MAGIC_U32 0x54534150UL /* "PAST" little-endian */

#define PA_IMG_HEADER_VERSION 1U
#define PA_STATE_VERSION 1U

#define PA_SLOT_A 0U
#define PA_SLOT_B 1U
#define PA_SLOT_NONE 0xFFU

#define PA_LAST_RESULT_UNKNOWN 0U
#define PA_LAST_RESULT_OK 1U
#define PA_LAST_RESULT_ROLLBACK 2U

#define PA_IMG_HEADER_SIZE 64U
#define PA_BOOT_STATE_SIZE 64U

#if defined(__GNUC__) || defined(__clang__)
#define PA_PACKED __attribute__((packed))
#else
#define PA_PACKED
#endif

/* Binary compatible with tools/pack_fw.py (64 bytes) */
typedef struct
{
  uint32_t magic_u32;         /* "PAFW" */
  uint16_t header_size;       /* 64 */
  uint16_t header_version;    /* 1 */
  uint32_t image_size;
  uint32_t image_crc32;
  uint16_t ver_major;
  uint16_t ver_minor;
  uint16_t ver_patch;
  uint32_t build_unix;
  uint8_t board_id[16];
  uint8_t git_sha[12];
  uint8_t reserved[10];
} PA_PACKED pa_image_header_t;

/* Binary compatible with docs/protocol/v2_boot_state_layout.md (64 bytes) */
typedef struct
{
  uint32_t magic_u32;         /* "PAST" */
  uint16_t state_version;     /* 1 */
  uint8_t active_slot;        /* A/B */
  uint8_t pending_slot;       /* A/B/NONE */
  uint8_t boot_attempts;
  uint8_t last_result;
  uint32_t seq;
  uint32_t slot_a_size;
  uint32_t slot_a_crc32;
  uint32_t slot_b_size;
  uint32_t slot_b_crc32;
  uint8_t reserved[30];
  uint32_t crc32;
} PA_PACKED pa_boot_state_t;

#if defined(__STDC_VERSION__) && (__STDC_VERSION__ >= 201112L)
_Static_assert(sizeof(pa_image_header_t) == PA_IMG_HEADER_SIZE, "pa_image_header_t must be 64 bytes");
_Static_assert(sizeof(pa_boot_state_t) == PA_BOOT_STATE_SIZE, "pa_boot_state_t must be 64 bytes");
#endif

#ifdef __cplusplus
}
#endif

#endif /* PA_BOOT_PROTOCOL_H */
