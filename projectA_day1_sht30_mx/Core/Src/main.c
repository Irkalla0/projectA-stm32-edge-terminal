/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Main program body
  ******************************************************************************
  * @attention
  *
  * Copyright (c) 2026 STMicroelectronics.
  * All rights reserved.
  *
  * This software is licensed under terms that can be found in the LICENSE file
  * in the root directory of this software component.
  * If no LICENSE file comes with this software, it is provided AS-IS.
  *
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "cmsis_os.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */
#define SHT30_ADDR_44 (0x44 << 1)
#define SHT30_ADDR_45 (0x45 << 1)
#define VL53L0X_ADDR (0x29 << 1)
#define INA219_ADDR (0x40 << 1)
#define I2C_IO_TIMEOUT_MS 50U

typedef enum
{
  SENSOR_NONE = 0,
  SENSOR_SHT3X
} sensor_type_t;

typedef enum
{
  UPG_STATE_IDLE = 0,
  UPG_STATE_RECEIVING,
  UPG_STATE_RECEIVED,
  UPG_STATE_ACTIVATING,
  UPG_STATE_PENDING_CONFIRM,
  UPG_STATE_CONFIRMED,
  UPG_STATE_ROLLBACK_REQUIRED,
  UPG_STATE_ERROR
} upgrade_state_t;

typedef struct
{
  uint8_t active_slot;
  uint8_t pending_slot;
  uint8_t boot_attempts;
  uint8_t last_result;
  uint32_t seq;
  uint32_t slot_a_size;
  uint32_t slot_a_crc32;
  uint32_t slot_b_size;
  uint32_t slot_b_crc32;
} boot_state_t;

typedef struct
{
  uint32_t magic;
  uint32_t version;
  boot_state_t state;
  uint32_t crc32;
} boot_state_record_t;

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */
#define APP_VERSION_STR "1.5.0"
#define BOOT_VERSION_STR "0.1.0"
#define UPG_MAX_CHUNK_BYTES 128U
#define UPG_CMD_BUF_SIZE 384U
#define UPG_MAX_IMAGE_BYTES (1024U * 1024U)
#define UPG_TRIAL_MAX_ATTEMPTS 3U
#define BOOT_SLOT_A 0U
#define BOOT_SLOT_B 1U
#define BOOT_SLOT_NONE 0xFFU
#define BOOT_RESULT_UNKNOWN 0U
#define BOOT_RESULT_OK 1U
#define BOOT_RESULT_ROLLBACK 2U
#define W25_SPI_TIMEOUT_MS 100U
#define W25_READY_TIMEOUT_MS 3000U
#define W25_CS_GPIO_Port GPIOB
#define W25_CS_Pin GPIO_PIN_12
#define W25_JEDEC_ID_W25Q128 0xEF4018UL
#define W25_BOOT_META_ADDR 0x00FF0000UL
#define W25_BOOT_META_MAGIC 0x42535445UL /* "BSTE" */
#define W25_BOOT_META_VERSION 0x00000001UL
#define CAN_HOST_TO_DEV_STDID 0x321U
#define CAN_DEV_TO_HOST_STDID 0x322U
#define CAN_PKT_SEG 0x01U
#define CAN_PKT_EOM 0x02U
#define CAN_PKT_ACK 0xA0U
#define CAN_PKT_NACK 0xA1U
#define CAN_MAX_SEG_BYTES 5U

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
I2C_HandleTypeDef hi2c1;
I2C_HandleTypeDef hi2c2;
SPI_HandleTypeDef hspi1;
CAN_HandleTypeDef hcan1;

UART_HandleTypeDef huart1;
UART_HandleTypeDef huart2;

/* Definitions for defaultTask */
osThreadId_t defaultTaskHandle;
const osThreadAttr_t defaultTask_attributes = {
  .name = "defaultTask",
  .stack_size = 256 * 4,
  .priority = (osPriority_t) osPriorityNormal,
};
/* USER CODE BEGIN PV */
osThreadId_t sampleTaskHandle;
const osThreadAttr_t sampleTask_attributes = {
  .name = "sampleTask",
  .stack_size = 1024 * 4,
  .priority = (osPriority_t) osPriorityNormal,
};

osThreadId_t cmdTaskHandle;
const osThreadAttr_t cmdTask_attributes = {
  .name = "cmdTask",
  /* UPG_DATA command parsing uses large local buffers and printf/sscanf;
   * keep a larger margin to avoid stack overflow under noisy UART traffic. */
  .stack_size = 1024 * 4,
  .priority = (osPriority_t) osPriorityAboveNormal,
};

static uint16_t g_sensor_addr = 0;
static sensor_type_t g_sensor_type = SENSOR_NONE;
static I2C_HandleTypeDef *g_sensor_i2c = NULL;
static const char *g_sensor_bus = "none";
static I2C_HandleTypeDef *g_vl53_i2c = NULL;
static I2C_HandleTypeDef *g_ina219_i2c = NULL;
static uint8_t g_vl53_ok = 0U;
static uint8_t g_ina219_ok = 0U;
static uint8_t g_sim_mode = 0;
static float g_sim_t = 25.0f;
static float g_sim_h = 50.0f;
static uint16_t g_sim_dist_mm = 1200;
static uint16_t g_sim_curr_ma = 350;
static uint16_t g_frame_seq = 0;
static uint32_t g_sample_period_ms = 1000;
static float g_temp_alarm_th_c = 28.5f;
static float g_hum_alarm_th_rh = 68.0f;
static uint16_t g_dist_alarm_th_mm = 600;
static uint16_t g_curr_alarm_th_ma = 900;
typedef struct
{
  char buf[UPG_CMD_BUF_SIZE];
  uint16_t len;
} cmd_rx_ctx_t;
typedef struct
{
  char buf[UPG_CMD_BUF_SIZE];
  uint16_t len;
  uint8_t seq;
} can_rx_ctx_t;
static cmd_rx_ctx_t g_cmd_rx_uart1 = {{0}, 0};
static cmd_rx_ctx_t g_cmd_rx_uart2 = {{0}, 0};
static can_rx_ctx_t g_cmd_rx_can = {{0}, 0, 0};
static uint32_t g_last_sample_tick = 0;
static upgrade_state_t g_upg_state = UPG_STATE_IDLE;
static uint32_t g_upg_expected_size = 0;
static uint32_t g_upg_expected_crc32 = 0;
static uint32_t g_upg_received = 0;
static uint32_t g_upg_running_crc32 = 0xFFFFFFFFU;
static char g_upg_last_err[16] = "OK";
static char g_upg_version[16] = "0.0.0";
static uint8_t g_upg_target_slot = BOOT_SLOT_B;
static boot_state_t g_boot_state = {
    .active_slot = BOOT_SLOT_A,
    .pending_slot = BOOT_SLOT_NONE,
    .boot_attempts = 0,
    .last_result = BOOT_RESULT_UNKNOWN,
    .seq = 0,
    .slot_a_size = 0,
    .slot_a_crc32 = 0,
    .slot_b_size = 0,
    .slot_b_crc32 = 0};
static uint8_t g_w25_ready = 0U;
static uint32_t g_w25_jedec_id = 0U;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_I2C1_Init(void);
static void MX_I2C2_Init(void);
static void MX_SPI1_Init(void);
static void MX_CAN1_Init(void);
static void MX_USART1_UART_Init(void);
static void MX_USART2_UART_Init(void);
void StartDefaultTask(void *argument);

/* USER CODE BEGIN PFP */
static void I2C_PrintScan(I2C_HandleTypeDef *hi2c, const char *bus_name);
static void I2C_PrintScanAll(void);
static void Sensor_Detect(void);
static HAL_StatusTypeDef Sensor_Read(float *temp_c, float *hum_rh);
static HAL_StatusTypeDef VL53L0X_ReadDistanceMm(uint16_t *dist_mm);
static HAL_StatusTypeDef INA219_ReadCurrentMa(uint16_t *curr_ma);
static uint16_t CRC16_Modbus(const uint8_t *data, uint16_t len);
static uint32_t CRC32_UpdateRaw(uint32_t crc, const uint8_t *data, uint16_t len);
static void Protocol_PrintFrameHex(uint8_t cmd, int16_t temp_centi, uint16_t hum_centi);
static void Protocol_ProcessCommand(const char *cmd);
static void Protocol_HandleRxByte(cmd_rx_ctx_t *ctx, uint8_t ch);
static void Protocol_HandleCanFrame(const CAN_RxHeaderTypeDef *hdr, const uint8_t *data);
static void Protocol_PollRx(void);
static void CAN_SendPacket(uint8_t type, uint8_t seq, uint8_t code);
static void App_TaskStep(void);
static int ParseU32Token(const char *text, uint32_t *out);
static int ParseHexBytes(const char *hex, uint8_t *out, uint16_t max_len, uint16_t *out_len);
static const char *Upg_StateName(upgrade_state_t state);
static const char *Boot_SlotName(uint8_t slot);
static const char *Boot_ResultName(uint8_t result);
static uint8_t Boot_OtherSlot(uint8_t slot);
static void Boot_SetSlotMeta(uint8_t slot, uint32_t size, uint32_t crc32);
static void Boot_MarkPending(uint8_t slot);
static void Boot_ConfirmPending(void);
static void Boot_MarkRollback(void);
static void Boot_PrintState(void);
static HAL_StatusTypeDef W25_Init(void);
static HAL_StatusTypeDef W25_ReadJedecId(uint32_t *id);
static HAL_StatusTypeDef W25_WriteEnable(void);
static HAL_StatusTypeDef W25_ReadStatus1(uint8_t *status1);
static HAL_StatusTypeDef W25_WaitReady(uint32_t timeout_ms);
static HAL_StatusTypeDef W25_ReadData(uint32_t addr, uint8_t *buf, uint16_t len);
static HAL_StatusTypeDef W25_PageProgram(uint32_t addr, const uint8_t *buf, uint16_t len);
static HAL_StatusTypeDef W25_SectorErase4K(uint32_t addr);
static void Boot_LoadFromW25(void);
static void Boot_SaveToW25(void);
static void Upg_SetErrText(const char *err);
static void Upg_SetErr(const char *err);
static void Upg_ResetSession(void);
void StartSampleTask(void *argument);
void StartCmdTask(void *argument);

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
int __io_putchar(int ch)
{
  HAL_UART_Transmit(&huart1, (uint8_t *)&ch, 1, HAL_MAX_DELAY);
  HAL_UART_Transmit(&huart2, (uint8_t *)&ch, 1, HAL_MAX_DELAY);
  return ch;
}

static uint16_t CRC16_Modbus(const uint8_t *data, uint16_t len)
{
  uint16_t crc = 0xFFFF;
  for (uint16_t i = 0; i < len; i++)
  {
    crc ^= data[i];
    for (uint8_t j = 0; j < 8; j++)
    {
      if (crc & 0x0001)
        crc = (crc >> 1) ^ 0xA001;
      else
        crc >>= 1;
    }
  }
  return crc;
}

static uint32_t CRC32_UpdateRaw(uint32_t crc, const uint8_t *data, uint16_t len)
{
  for (uint16_t i = 0; i < len; i++)
  {
    crc ^= data[i];
    for (uint8_t b = 0; b < 8; b++)
    {
      if (crc & 1U)
        crc = (crc >> 1) ^ 0xEDB88320U;
      else
        crc >>= 1;
    }
  }
  return crc;
}

static int ParseU32Token(const char *text, uint32_t *out)
{
  char *endptr = NULL;
  unsigned long value = strtoul(text, &endptr, 0);
  if (text[0] == '-' || text == endptr || (endptr && *endptr != '\0') || value > 0xFFFFFFFFUL)
    return 0;
  *out = (uint32_t)value;
  return 1;
}

static int HexNibble(char ch)
{
  if (ch >= '0' && ch <= '9')
    return ch - '0';
  if (ch >= 'A' && ch <= 'F')
    return ch - 'A' + 10;
  if (ch >= 'a' && ch <= 'f')
    return ch - 'a' + 10;
  return -1;
}

static int ParseHexBytes(const char *hex, uint8_t *out, uint16_t max_len, uint16_t *out_len)
{
  uint16_t hex_len = (uint16_t)strlen(hex);
  if (hex_len == 0 || (hex_len % 2U) != 0U)
    return -1;
  if ((hex_len / 2U) > max_len)
    return -1;

  for (uint16_t i = 0; i < (hex_len / 2U); i++)
  {
    int hi = HexNibble(hex[2U * i]);
    int lo = HexNibble(hex[2U * i + 1U]);
    if (hi < 0 || lo < 0)
      return -1;
    out[i] = (uint8_t)((hi << 4) | lo);
  }

  *out_len = (uint16_t)(hex_len / 2U);
  return 0;
}

static const char *Upg_StateName(upgrade_state_t state)
{
  switch (state)
  {
  case UPG_STATE_IDLE:
    return "idle";
  case UPG_STATE_RECEIVING:
    return "receiving";
  case UPG_STATE_RECEIVED:
    return "received";
  case UPG_STATE_ACTIVATING:
    return "activating";
  case UPG_STATE_PENDING_CONFIRM:
    return "pending_confirm";
  case UPG_STATE_CONFIRMED:
    return "confirmed";
  case UPG_STATE_ROLLBACK_REQUIRED:
    return "rollback_required";
  case UPG_STATE_ERROR:
    return "error";
  default:
    return "unknown";
  }
}

static const char *Boot_SlotName(uint8_t slot)
{
  switch (slot)
  {
  case BOOT_SLOT_A:
    return "A";
  case BOOT_SLOT_B:
    return "B";
  case BOOT_SLOT_NONE:
    return "NONE";
  default:
    return "UNKNOWN";
  }
}

static const char *Boot_ResultName(uint8_t result)
{
  switch (result)
  {
  case BOOT_RESULT_OK:
    return "ok";
  case BOOT_RESULT_ROLLBACK:
    return "rollback";
  case BOOT_RESULT_UNKNOWN:
  default:
    return "unknown";
  }
}

static uint8_t Boot_OtherSlot(uint8_t slot)
{
  return (slot == BOOT_SLOT_B) ? BOOT_SLOT_A : BOOT_SLOT_B;
}

static void Boot_SetSlotMeta(uint8_t slot, uint32_t size, uint32_t crc32)
{
  if (slot == BOOT_SLOT_A)
  {
    g_boot_state.slot_a_size = size;
    g_boot_state.slot_a_crc32 = crc32;
  }
  else if (slot == BOOT_SLOT_B)
  {
    g_boot_state.slot_b_size = size;
    g_boot_state.slot_b_crc32 = crc32;
  }
  Boot_SaveToW25();
}

static void Boot_MarkPending(uint8_t slot)
{
  g_boot_state.pending_slot = slot;
  g_boot_state.boot_attempts = 0;
  g_boot_state.last_result = BOOT_RESULT_UNKNOWN;
  g_boot_state.seq++;
  Boot_SaveToW25();
}

static void Boot_ConfirmPending(void)
{
  if (g_boot_state.pending_slot == BOOT_SLOT_A || g_boot_state.pending_slot == BOOT_SLOT_B)
    g_boot_state.active_slot = g_boot_state.pending_slot;
  g_boot_state.pending_slot = BOOT_SLOT_NONE;
  g_boot_state.boot_attempts = 0;
  g_boot_state.last_result = BOOT_RESULT_OK;
  g_boot_state.seq++;
  g_upg_target_slot = Boot_OtherSlot(g_boot_state.active_slot);
  Boot_SaveToW25();
}

static void Boot_MarkRollback(void)
{
  g_boot_state.pending_slot = BOOT_SLOT_NONE;
  g_boot_state.boot_attempts = 0;
  g_boot_state.last_result = BOOT_RESULT_ROLLBACK;
  g_boot_state.seq++;
  g_upg_target_slot = Boot_OtherSlot(g_boot_state.active_slot);
  Boot_SaveToW25();
}

static void Boot_PrintState(void)
{
  printf("BOOT:active=%s,pending=%s,attempts=%u,last=%s,seq=%lu,slotA=%lu/0x%08lX,slotB=%lu/0x%08lX\r\n",
         Boot_SlotName(g_boot_state.active_slot),
         Boot_SlotName(g_boot_state.pending_slot),
         (unsigned int)g_boot_state.boot_attempts,
         Boot_ResultName(g_boot_state.last_result),
         (unsigned long)g_boot_state.seq,
         (unsigned long)g_boot_state.slot_a_size,
         (unsigned long)g_boot_state.slot_a_crc32,
         (unsigned long)g_boot_state.slot_b_size,
         (unsigned long)g_boot_state.slot_b_crc32);
}

static void W25_CS_Low(void)
{
  HAL_GPIO_WritePin(W25_CS_GPIO_Port, W25_CS_Pin, GPIO_PIN_RESET);
}

static void W25_CS_High(void)
{
  HAL_GPIO_WritePin(W25_CS_GPIO_Port, W25_CS_Pin, GPIO_PIN_SET);
}

static HAL_StatusTypeDef W25_ReadJedecId(uint32_t *id)
{
  uint8_t tx[4] = {0x9FU, 0xFFU, 0xFFU, 0xFFU};
  uint8_t rx[4] = {0};
  if (id == NULL)
    return HAL_ERROR;

  W25_CS_Low();
  if (HAL_SPI_TransmitReceive(&hspi1, tx, rx, 4, W25_SPI_TIMEOUT_MS) != HAL_OK)
  {
    W25_CS_High();
    return HAL_ERROR;
  }
  W25_CS_High();
  *id = ((uint32_t)rx[1] << 16) | ((uint32_t)rx[2] << 8) | (uint32_t)rx[3];
  return HAL_OK;
}

static HAL_StatusTypeDef W25_WriteEnable(void)
{
  uint8_t cmd = 0x06U;
  W25_CS_Low();
  if (HAL_SPI_Transmit(&hspi1, &cmd, 1, W25_SPI_TIMEOUT_MS) != HAL_OK)
  {
    W25_CS_High();
    return HAL_ERROR;
  }
  W25_CS_High();
  return HAL_OK;
}

static HAL_StatusTypeDef W25_ReadStatus1(uint8_t *status1)
{
  uint8_t tx[2] = {0x05U, 0xFFU};
  uint8_t rx[2] = {0};
  if (status1 == NULL)
    return HAL_ERROR;

  W25_CS_Low();
  if (HAL_SPI_TransmitReceive(&hspi1, tx, rx, 2, W25_SPI_TIMEOUT_MS) != HAL_OK)
  {
    W25_CS_High();
    return HAL_ERROR;
  }
  W25_CS_High();
  *status1 = rx[1];
  return HAL_OK;
}

static HAL_StatusTypeDef W25_WaitReady(uint32_t timeout_ms)
{
  uint32_t start = HAL_GetTick();
  uint8_t sr1 = 0;
  while ((HAL_GetTick() - start) < timeout_ms)
  {
    if (W25_ReadStatus1(&sr1) != HAL_OK)
      return HAL_ERROR;
    if ((sr1 & 0x01U) == 0U)
      return HAL_OK;
    HAL_Delay(1);
  }
  return HAL_TIMEOUT;
}

static HAL_StatusTypeDef W25_ReadData(uint32_t addr, uint8_t *buf, uint16_t len)
{
  uint8_t cmd[4] = {
      0x03U,
      (uint8_t)((addr >> 16) & 0xFFU),
      (uint8_t)((addr >> 8) & 0xFFU),
      (uint8_t)(addr & 0xFFU)};

  if (buf == NULL || len == 0U)
    return HAL_ERROR;

  W25_CS_Low();
  if (HAL_SPI_Transmit(&hspi1, cmd, sizeof(cmd), W25_SPI_TIMEOUT_MS) != HAL_OK)
  {
    W25_CS_High();
    return HAL_ERROR;
  }
  if (HAL_SPI_Receive(&hspi1, buf, len, W25_SPI_TIMEOUT_MS) != HAL_OK)
  {
    W25_CS_High();
    return HAL_ERROR;
  }
  W25_CS_High();
  return HAL_OK;
}

static HAL_StatusTypeDef W25_PageProgram(uint32_t addr, const uint8_t *buf, uint16_t len)
{
  uint8_t cmd[4] = {
      0x02U,
      (uint8_t)((addr >> 16) & 0xFFU),
      (uint8_t)((addr >> 8) & 0xFFU),
      (uint8_t)(addr & 0xFFU)};

  if (buf == NULL || len == 0U || len > 256U)
    return HAL_ERROR;
  if (((addr & 0xFFU) + len) > 256U)
    return HAL_ERROR;
  if (W25_WriteEnable() != HAL_OK)
    return HAL_ERROR;

  W25_CS_Low();
  if (HAL_SPI_Transmit(&hspi1, cmd, sizeof(cmd), W25_SPI_TIMEOUT_MS) != HAL_OK)
  {
    W25_CS_High();
    return HAL_ERROR;
  }
  if (HAL_SPI_Transmit(&hspi1, (uint8_t *)buf, len, W25_SPI_TIMEOUT_MS) != HAL_OK)
  {
    W25_CS_High();
    return HAL_ERROR;
  }
  W25_CS_High();
  return W25_WaitReady(W25_READY_TIMEOUT_MS);
}

static HAL_StatusTypeDef W25_SectorErase4K(uint32_t addr)
{
  uint8_t cmd[4] = {
      0x20U,
      (uint8_t)((addr >> 16) & 0xFFU),
      (uint8_t)((addr >> 8) & 0xFFU),
      (uint8_t)(addr & 0xFFU)};

  if (W25_WriteEnable() != HAL_OK)
    return HAL_ERROR;

  W25_CS_Low();
  if (HAL_SPI_Transmit(&hspi1, cmd, sizeof(cmd), W25_SPI_TIMEOUT_MS) != HAL_OK)
  {
    W25_CS_High();
    return HAL_ERROR;
  }
  W25_CS_High();
  return W25_WaitReady(W25_READY_TIMEOUT_MS);
}

static HAL_StatusTypeDef W25_Init(void)
{
  uint32_t id = 0;

  W25_CS_High();
  HAL_Delay(1);

  if (W25_ReadJedecId(&id) != HAL_OK)
    return HAL_ERROR;

  g_w25_jedec_id = id;
  if (id == 0x000000UL || id == 0xFFFFFFUL)
    return HAL_ERROR;

  g_w25_ready = 1U;
  return HAL_OK;
}

static void Boot_LoadFromW25(void)
{
  boot_state_record_t rec = {0};
  uint32_t calc_crc = 0;

  if (!g_w25_ready)
    return;

  if (W25_ReadData(W25_BOOT_META_ADDR, (uint8_t *)&rec, (uint16_t)sizeof(rec)) != HAL_OK)
  {
    printf("BOOT_META:load_err\r\n");
    return;
  }

  calc_crc = CRC32_UpdateRaw(0xFFFFFFFFU, (const uint8_t *)&rec, (uint16_t)(sizeof(rec) - sizeof(rec.crc32))) ^ 0xFFFFFFFFU;
  if (rec.magic != W25_BOOT_META_MAGIC || rec.version != W25_BOOT_META_VERSION || rec.crc32 != calc_crc)
  {
    Boot_SaveToW25();
    printf("BOOT_META:init_default\r\n");
    return;
  }

  g_boot_state = rec.state;
  if (g_boot_state.active_slot != BOOT_SLOT_A && g_boot_state.active_slot != BOOT_SLOT_B)
    g_boot_state.active_slot = BOOT_SLOT_A;
  if (g_boot_state.pending_slot != BOOT_SLOT_A && g_boot_state.pending_slot != BOOT_SLOT_B && g_boot_state.pending_slot != BOOT_SLOT_NONE)
    g_boot_state.pending_slot = BOOT_SLOT_NONE;
  g_upg_target_slot = Boot_OtherSlot(g_boot_state.active_slot);
  printf("BOOT_META:loaded seq=%lu\r\n", (unsigned long)g_boot_state.seq);
}

static void Boot_SaveToW25(void)
{
  boot_state_record_t rec = {0};

  if (!g_w25_ready)
    return;

  rec.magic = W25_BOOT_META_MAGIC;
  rec.version = W25_BOOT_META_VERSION;
  rec.state = g_boot_state;
  rec.crc32 = CRC32_UpdateRaw(0xFFFFFFFFU, (const uint8_t *)&rec, (uint16_t)(sizeof(rec) - sizeof(rec.crc32))) ^ 0xFFFFFFFFU;

  if (W25_SectorErase4K(W25_BOOT_META_ADDR) != HAL_OK)
  {
    printf("BOOT_META:save_err:erase\r\n");
    return;
  }
  if (W25_PageProgram(W25_BOOT_META_ADDR, (const uint8_t *)&rec, (uint16_t)sizeof(rec)) != HAL_OK)
  {
    printf("BOOT_META:save_err:prog\r\n");
  }
}

static void Upg_SetErrText(const char *err)
{
  size_t n = strlen(err);
  if (n >= sizeof(g_upg_last_err))
    n = sizeof(g_upg_last_err) - 1U;
  memcpy(g_upg_last_err, err, n);
  g_upg_last_err[n] = '\0';
}

static void Upg_SetErr(const char *err)
{
  Upg_SetErrText(err);
  g_upg_state = UPG_STATE_ERROR;
}

static void Upg_ResetSession(void)
{
  g_upg_state = UPG_STATE_IDLE;
  g_upg_expected_size = 0;
  g_upg_expected_crc32 = 0;
  g_upg_received = 0;
  g_upg_running_crc32 = 0xFFFFFFFFU;
  g_upg_target_slot = Boot_OtherSlot(g_boot_state.active_slot);
  Upg_SetErrText("OK");
}

static void Protocol_PrintFrameHex(uint8_t cmd, int16_t temp_centi, uint16_t hum_centi)
{
  uint8_t frame[32];
  uint16_t idx = 0;
  const uint16_t payload_len = 4;
  const uint16_t seq = g_frame_seq++;
  const uint32_t ts = HAL_GetTick();

  frame[idx++] = 0xAA;
  frame[idx++] = 0x55;
  frame[idx++] = cmd;
  frame[idx++] = (uint8_t)(payload_len & 0xFF);
  frame[idx++] = (uint8_t)((payload_len >> 8) & 0xFF);
  frame[idx++] = (uint8_t)(seq & 0xFF);
  frame[idx++] = (uint8_t)((seq >> 8) & 0xFF);
  frame[idx++] = (uint8_t)(ts & 0xFF);
  frame[idx++] = (uint8_t)((ts >> 8) & 0xFF);
  frame[idx++] = (uint8_t)((ts >> 16) & 0xFF);
  frame[idx++] = (uint8_t)((ts >> 24) & 0xFF);
  frame[idx++] = (uint8_t)(temp_centi & 0xFF);
  frame[idx++] = (uint8_t)((temp_centi >> 8) & 0xFF);
  frame[idx++] = (uint8_t)(hum_centi & 0xFF);
  frame[idx++] = (uint8_t)((hum_centi >> 8) & 0xFF);

  uint16_t crc = CRC16_Modbus(frame, idx);
  frame[idx++] = (uint8_t)(crc & 0xFF);
  frame[idx++] = (uint8_t)((crc >> 8) & 0xFF);

  printf("FRAME_HEX:");
  for (uint16_t i = 0; i < idx; i++)
    printf(" %02X", frame[i]);
  printf("\r\n");
}

static void Protocol_ProcessCommand(const char *cmd)
{
  char cmd_trim[UPG_CMD_BUF_SIZE];
  size_t len = strlen(cmd);
  size_t start = 0;
  size_t end = len;

  while (start < len && (cmd[start] == ' ' || cmd[start] == '\t'))
    start++;
  while (end > start && (cmd[end - 1] == ' ' || cmd[end - 1] == '\t'))
    end--;

  len = end - start;
  if (len >= sizeof(cmd_trim))
    len = sizeof(cmd_trim) - 1;
  memcpy(cmd_trim, &cmd[start], len);
  cmd_trim[len] = '\0';

  if (strncmp(cmd_trim, "SET_PERIOD", 10) == 0)
  {
    const char *p = cmd_trim + 10;
    char *endptr = NULL;
    uint32_t v = 0;

    while (*p == ' ' || *p == '\t' || *p == '=' || *p == ':')
      p++;

    v = strtoul(p, &endptr, 10);
    while (endptr && (*endptr == ' ' || *endptr == '\t'))
      endptr++;

    if (endptr == p || (endptr && *endptr != '\0'))
    {
      printf("SET_PERIOD_ERR:FORMAT\r\n");
    }
    else if (v >= 100 && v <= 5000)
    {
      g_sample_period_ms = v;
      printf("SET_PERIOD_OK:%lu\r\n", (unsigned long)g_sample_period_ms);
    }
    else
    {
      printf("SET_PERIOD_ERR:RANGE(100-5000)\r\n");
    }
    return;
  }

  if (strncmp(cmd_trim, "SET_THR_T", 9) == 0)
  {
    const char *p = cmd_trim + 9;
    char *endptr = NULL;
    float v = 0.0f;

    while (*p == ' ' || *p == '\t' || *p == '=' || *p == ':')
      p++;

    v = strtof(p, &endptr);
    while (endptr && (*endptr == ' ' || *endptr == '\t'))
      endptr++;

    if (endptr == p || (endptr && *endptr != '\0'))
      printf("SET_THR_T_ERR:FORMAT\r\n");
    else if (v >= 0.0f && v <= 80.0f)
    {
      g_temp_alarm_th_c = v;
      printf("SET_THR_T_OK:%.2f\r\n", g_temp_alarm_th_c);
    }
    else
      printf("SET_THR_T_ERR:RANGE(0-80)\r\n");
    return;
  }

  if (strncmp(cmd_trim, "SET_THR_H", 9) == 0)
  {
    const char *p = cmd_trim + 9;
    char *endptr = NULL;
    float v = 0.0f;

    while (*p == ' ' || *p == '\t' || *p == '=' || *p == ':')
      p++;

    v = strtof(p, &endptr);
    while (endptr && (*endptr == ' ' || *endptr == '\t'))
      endptr++;

    if (endptr == p || (endptr && *endptr != '\0'))
      printf("SET_THR_H_ERR:FORMAT\r\n");
    else if (v >= 0.0f && v <= 100.0f)
    {
      g_hum_alarm_th_rh = v;
      printf("SET_THR_H_OK:%.2f\r\n", g_hum_alarm_th_rh);
    }
    else
      printf("SET_THR_H_ERR:RANGE(0-100)\r\n");
    return;
  }

  if (strncmp(cmd_trim, "SET_THR_D", 9) == 0)
  {
    const char *p = cmd_trim + 9;
    char *endptr = NULL;
    uint32_t v = 0;

    while (*p == ' ' || *p == '\t' || *p == '=' || *p == ':')
      p++;

    v = strtoul(p, &endptr, 10);
    while (endptr && (*endptr == ' ' || *endptr == '\t'))
      endptr++;

    if (endptr == p || (endptr && *endptr != '\0'))
      printf("SET_THR_D_ERR:FORMAT\r\n");
    else if (v >= 50 && v <= 4000)
    {
      g_dist_alarm_th_mm = (uint16_t)v;
      printf("SET_THR_D_OK:%u\r\n", g_dist_alarm_th_mm);
    }
    else
      printf("SET_THR_D_ERR:RANGE(50-4000)\r\n");
    return;
  }

  if (strncmp(cmd_trim, "SET_THR_I", 9) == 0)
  {
    const char *p = cmd_trim + 9;
    char *endptr = NULL;
    uint32_t v = 0;

    while (*p == ' ' || *p == '\t' || *p == '=' || *p == ':')
      p++;

    v = strtoul(p, &endptr, 10);
    while (endptr && (*endptr == ' ' || *endptr == '\t'))
      endptr++;

    if (endptr == p || (endptr && *endptr != '\0'))
      printf("SET_THR_I_ERR:FORMAT\r\n");
    else if (v >= 100 && v <= 5000)
    {
      g_curr_alarm_th_ma = (uint16_t)v;
      printf("SET_THR_I_OK:%u\r\n", g_curr_alarm_th_ma);
    }
    else
      printf("SET_THR_I_ERR:RANGE(100-5000)\r\n");
    return;
  }

  if (strcmp(cmd_trim, "GET_PERIOD") == 0)
  {
    printf("PERIOD:%lu\r\n", (unsigned long)g_sample_period_ms);
    return;
  }

  if (strcmp(cmd_trim, "GET_THR") == 0)
  {
    printf("THR:T=%.2f,H=%.2f\r\n", g_temp_alarm_th_c, g_hum_alarm_th_rh);
    return;
  }

  if (strcmp(cmd_trim, "GET_THR2") == 0)
  {
    printf("THR2:D=%u,I=%u\r\n", g_dist_alarm_th_mm, g_curr_alarm_th_ma);
    return;
  }

  if (strcmp(cmd_trim, "GET_VER") == 0)
  {
    printf("VER:app=%s,boot=%s\r\n", APP_VERSION_STR, BOOT_VERSION_STR);
    return;
  }

  if (strcmp(cmd_trim, "GET_CAP") == 0)
  {
    printf("CAP:upgrade_uart=1,max_chunk=%u,dual_slot=1\r\n", (unsigned int)UPG_MAX_CHUNK_BYTES);
    return;
  }

  if (strcmp(cmd_trim, "GET_FLASH") == 0 || strcmp(cmd_trim, "FLASH_ID") == 0)
  {
    uint32_t id = 0;
    if (W25_ReadJedecId(&id) == HAL_OK)
    {
      g_w25_jedec_id = id;
      g_w25_ready = (id != 0x000000UL && id != 0xFFFFFFUL) ? 1U : 0U;
      printf("FLASH:id=0x%06lX,ready=%u,expect=0x%06lX\r\n",
             (unsigned long)g_w25_jedec_id,
             (unsigned int)g_w25_ready,
             (unsigned long)W25_JEDEC_ID_W25Q128);
    }
    else
    {
      g_w25_ready = 0U;
      printf("FLASH:ERR\r\n");
    }
    return;
  }

  if (strcmp(cmd_trim, "BOOT_SAVE") == 0)
  {
    if (!g_w25_ready)
    {
      printf("BOOT_SAVE:ERR:NO_FLASH\r\n");
      return;
    }
    Boot_SaveToW25();
    printf("BOOT_SAVE:OK\r\n");
    Boot_PrintState();
    return;
  }

  if (strcmp(cmd_trim, "BOOT_LOAD") == 0)
  {
    if (!g_w25_ready)
    {
      printf("BOOT_LOAD:ERR:NO_FLASH\r\n");
      return;
    }
    Boot_LoadFromW25();
    printf("BOOT_LOAD:OK\r\n");
    Boot_PrintState();
    return;
  }

  if (strcmp(cmd_trim, "GET_BOOTSTATE") == 0)
  {
    Boot_PrintState();
    return;
  }

  if (strcmp(cmd_trim, "UPG_STATUS") == 0)
  {
    printf("UPG_STATUS:%s,off=%lu,err=%s\r\n", Upg_StateName(g_upg_state), (unsigned long)g_upg_received, g_upg_last_err);
    return;
  }

  if (strncmp(cmd_trim, "UPG_BEGIN", 9) == 0)
  {
    char ver[16] = {0};
    char size_token[32] = {0};
    char crc_token[32] = {0};
    uint32_t size = 0;
    uint32_t image_crc = 0;
    if (sscanf(cmd_trim, "UPG_BEGIN %15s %31s %31s", ver, size_token, crc_token) != 3)
    {
      Upg_SetErr("E_ARG");
      printf("UPG_NACK BEGIN E_ARG\r\n");
      return;
    }
    if (!ParseU32Token(size_token, &size) || !ParseU32Token(crc_token, &image_crc) || size == 0U || size > UPG_MAX_IMAGE_BYTES)
    {
      Upg_SetErr("E_ARG");
      printf("UPG_NACK BEGIN E_ARG\r\n");
      return;
    }
    if (g_boot_state.pending_slot != BOOT_SLOT_NONE)
    {
      Upg_SetErr("E_STATE");
      printf("UPG_NACK BEGIN E_STATE\r\n");
      return;
    }

    memset(g_upg_version, 0, sizeof(g_upg_version));
    strncpy(g_upg_version, ver, sizeof(g_upg_version) - 1U);
    g_upg_expected_size = size;
    g_upg_expected_crc32 = image_crc;
    g_upg_received = 0;
    g_upg_running_crc32 = 0xFFFFFFFFU;
    g_upg_target_slot = Boot_OtherSlot(g_boot_state.active_slot);
    g_upg_state = UPG_STATE_RECEIVING;
    Upg_SetErrText("OK");
    printf("UPG_ACK BEGIN off=0\r\n");
    printf("UPG_INFO target_slot=%s,ver=%s\r\n", Boot_SlotName(g_upg_target_slot), g_upg_version);
    return;
  }

  if (strncmp(cmd_trim, "UPG_DATA", 8) == 0)
  {
    char off_token[32] = {0};
    char payload_hex[(UPG_MAX_CHUNK_BYTES * 2U) + 1U] = {0};
    char crc_token[32] = {0};
    uint8_t chunk[UPG_MAX_CHUNK_BYTES];
    uint16_t chunk_len = 0;
    uint32_t offset = 0;
    uint32_t chunk_crc = 0;
    uint32_t calc_chunk_crc = 0;

    if (g_upg_state != UPG_STATE_RECEIVING)
    {
      Upg_SetErr("E_STATE");
      printf("UPG_NACK DATA E_STATE\r\n");
      return;
    }

    if (sscanf(cmd_trim, "UPG_DATA %31s %256s %31s", off_token, payload_hex, crc_token) != 3)
    {
      Upg_SetErr("E_ARG");
      printf("UPG_NACK DATA E_ARG\r\n");
      return;
    }

    if (!ParseU32Token(off_token, &offset) || !ParseU32Token(crc_token, &chunk_crc))
    {
      Upg_SetErr("E_ARG");
      printf("UPG_NACK DATA E_ARG\r\n");
      return;
    }

    if (offset != g_upg_received)
    {
      Upg_SetErr("E_OFF");
      printf("UPG_NACK DATA E_OFF\r\n");
      return;
    }

    if (ParseHexBytes(payload_hex, chunk, UPG_MAX_CHUNK_BYTES, &chunk_len) != 0)
    {
      Upg_SetErr("E_ARG");
      printf("UPG_NACK DATA E_ARG\r\n");
      return;
    }

    if ((g_upg_received + chunk_len) > g_upg_expected_size)
    {
      Upg_SetErr("E_OFF");
      printf("UPG_NACK DATA E_OFF\r\n");
      return;
    }

    calc_chunk_crc = CRC32_UpdateRaw(0xFFFFFFFFU, chunk, chunk_len) ^ 0xFFFFFFFFU;
    if (calc_chunk_crc != chunk_crc)
    {
      Upg_SetErr("E_CRC_CHUNK");
      printf("UPG_NACK DATA E_CRC_CHUNK\r\n");
      return;
    }

    g_upg_running_crc32 = CRC32_UpdateRaw(g_upg_running_crc32, chunk, chunk_len);
    g_upg_received += chunk_len;
    Upg_SetErrText("OK");
    printf("UPG_ACK DATA off=%lu\r\n", (unsigned long)g_upg_received);
    return;
  }

  if (strcmp(cmd_trim, "UPG_END") == 0)
  {
    uint32_t image_crc = 0;
    if (g_upg_state != UPG_STATE_RECEIVING)
    {
      Upg_SetErr("E_STATE");
      printf("UPG_NACK END E_STATE\r\n");
      return;
    }
    if (g_upg_received != g_upg_expected_size)
    {
      Upg_SetErr("E_OFF");
      printf("UPG_NACK END E_OFF\r\n");
      return;
    }
    image_crc = g_upg_running_crc32 ^ 0xFFFFFFFFU;
    if (image_crc != g_upg_expected_crc32)
    {
      Upg_SetErr("E_CRC_IMAGE");
      printf("UPG_NACK END E_CRC_IMAGE\r\n");
      return;
    }
    Boot_SetSlotMeta(g_upg_target_slot, g_upg_expected_size, image_crc);
    g_upg_state = UPG_STATE_RECEIVED;
    Upg_SetErrText("OK");
    printf("UPG_ACK END\r\n");
    printf("UPG_INFO image_slot=%s,size=%lu,crc=0x%08lX\r\n",
           Boot_SlotName(g_upg_target_slot),
           (unsigned long)g_upg_expected_size,
           (unsigned long)image_crc);
    return;
  }

  if (strcmp(cmd_trim, "UPG_ACTIVATE") == 0)
  {
    if (g_upg_state != UPG_STATE_RECEIVED)
    {
      Upg_SetErr("E_STATE");
      printf("UPG_NACK ACTIVATE E_STATE\r\n");
      return;
    }
    g_upg_state = UPG_STATE_ACTIVATING;
    Boot_MarkPending(g_upg_target_slot);
    g_upg_state = UPG_STATE_PENDING_CONFIRM;
    Upg_SetErrText("OK");
    printf("UPG_ACK ACTIVATE\r\n");
    Boot_PrintState();
    return;
  }

  if (strcmp(cmd_trim, "UPG_CONFIRM") == 0)
  {
    if (g_upg_state != UPG_STATE_PENDING_CONFIRM || g_boot_state.pending_slot == BOOT_SLOT_NONE)
    {
      Upg_SetErr("E_STATE");
      printf("UPG_NACK CONFIRM E_STATE\r\n");
      return;
    }
    Boot_ConfirmPending();
    g_upg_state = UPG_STATE_CONFIRMED;
    Upg_SetErrText("OK");
    printf("UPG_ACK CONFIRM\r\n");
    Boot_PrintState();
    return;
  }

  if (strcmp(cmd_trim, "UPG_FAIL_ONCE") == 0)
  {
    if (g_boot_state.pending_slot == BOOT_SLOT_NONE)
    {
      Upg_SetErr("E_STATE");
      printf("UPG_NACK FAIL E_STATE\r\n");
      return;
    }
    if (g_boot_state.boot_attempts < 0xFFU)
      g_boot_state.boot_attempts++;
    if (g_boot_state.boot_attempts >= UPG_TRIAL_MAX_ATTEMPTS)
    {
      Boot_MarkRollback();
      g_upg_state = UPG_STATE_ROLLBACK_REQUIRED;
      Upg_SetErrText("E_TRIAL");
      printf("UPG_ACK FAIL ROLLBACK\r\n");
    }
    else
    {
      g_boot_state.seq++;
      Boot_SaveToW25();
      Upg_SetErrText("OK");
      printf("UPG_ACK FAIL attempts=%u\r\n", (unsigned int)g_boot_state.boot_attempts);
    }
    Boot_PrintState();
    return;
  }

  if (strcmp(cmd_trim, "UPG_ABORT") == 0)
  {
    if (g_upg_state == UPG_STATE_PENDING_CONFIRM && g_boot_state.pending_slot != BOOT_SLOT_NONE)
      Boot_MarkRollback();
    Upg_ResetSession();
    printf("UPG_ACK ABORT\r\n");
    Boot_PrintState();
    return;
  }

  if (cmd_trim[0] != '\0')
    printf("CMD_ERR:%s\r\n", cmd_trim);
}

static void Protocol_HandleRxByte(cmd_rx_ctx_t *ctx, uint8_t ch)
{
  if (ctx == NULL)
    return;

  if (ch == '\r')
    return;

  if (ch == '\n')
  {
    if (ctx->len > 0U)
    {
      ctx->buf[ctx->len] = '\0';
      Protocol_ProcessCommand(ctx->buf);
    }
    ctx->len = 0;
    return;
  }

  if (ch == '\t')
    ch = ' ';

  /* Ignore binary/noise bytes so a floating RX pin does not corrupt parser. */
  if (ch < 0x20U || ch > 0x7EU)
  {
    ctx->len = 0;
    return;
  }

  if (ctx->len < (UPG_CMD_BUF_SIZE - 1U))
  {
    ctx->buf[ctx->len++] = (char)ch;
  }
  else
  {
    ctx->len = 0;
  }
}

static void CAN_SendPacket(uint8_t type, uint8_t seq, uint8_t code)
{
  CAN_TxHeaderTypeDef tx = {0};
  uint8_t payload[8] = {0};
  uint32_t mailbox = 0;

  tx.StdId = CAN_DEV_TO_HOST_STDID;
  tx.ExtId = 0;
  tx.IDE = CAN_ID_STD;
  tx.RTR = CAN_RTR_DATA;
  tx.DLC = 3;
  tx.TransmitGlobalTime = DISABLE;

  payload[0] = type;
  payload[1] = seq;
  payload[2] = code;
  if (HAL_CAN_AddTxMessage(&hcan1, &tx, payload, &mailbox) != HAL_OK)
  {
    /* UART log still helps when CAN TX is busy. */
    printf("CAN_TX_ERR:type=%u,seq=%u\r\n", (unsigned int)type, (unsigned int)seq);
  }
}

static void Protocol_HandleCanFrame(const CAN_RxHeaderTypeDef *hdr, const uint8_t *data)
{
  uint8_t pkt_type = 0U;
  uint8_t seq = 0U;
  uint8_t seg_len = 0U;
  uint8_t frag_idx = 0U;

  if (hdr == NULL || data == NULL)
    return;
  if (hdr->IDE != CAN_ID_STD || hdr->StdId != CAN_HOST_TO_DEV_STDID || hdr->RTR != CAN_RTR_DATA)
    return;
  if (hdr->DLC < 2U)
    return;

  pkt_type = data[0];
  seq = data[1];
  if (pkt_type == CAN_PKT_SEG)
  {
    if (hdr->DLC < 4U)
    {
      CAN_SendPacket(CAN_PKT_NACK, seq, 1U);
      return;
    }
    seg_len = data[2];
    frag_idx = data[3];
    if (seg_len > CAN_MAX_SEG_BYTES || (4U + seg_len) > hdr->DLC)
    {
      CAN_SendPacket(CAN_PKT_NACK, seq, 2U);
      g_cmd_rx_can.len = 0U;
      return;
    }

    if (frag_idx == 0U)
    {
      g_cmd_rx_can.len = 0U;
      g_cmd_rx_can.seq = seq;
    }

    if ((g_cmd_rx_can.len + seg_len) >= (UPG_CMD_BUF_SIZE - 1U))
    {
      g_cmd_rx_can.len = 0U;
      CAN_SendPacket(CAN_PKT_NACK, seq, 3U);
      return;
    }

    memcpy(&g_cmd_rx_can.buf[g_cmd_rx_can.len], &data[4], seg_len);
    g_cmd_rx_can.len += seg_len;
    return;
  }

  if (pkt_type == CAN_PKT_EOM)
  {
    if (g_cmd_rx_can.len == 0U)
    {
      CAN_SendPacket(CAN_PKT_NACK, seq, 4U);
      return;
    }
    g_cmd_rx_can.buf[g_cmd_rx_can.len] = '\0';
    Protocol_ProcessCommand(g_cmd_rx_can.buf);
    g_cmd_rx_can.len = 0U;
    CAN_SendPacket(CAN_PKT_ACK, seq, 0U);
    return;
  }
}

static void Protocol_PollRx(void)
{
  uint8_t ch = 0;
  CAN_RxHeaderTypeDef rx_header = {0};
  uint8_t rx_data[8] = {0};
  while (HAL_UART_Receive(&huart1, &ch, 1, 0) == HAL_OK)
    Protocol_HandleRxByte(&g_cmd_rx_uart1, ch);
  while (HAL_UART_Receive(&huart2, &ch, 1, 0) == HAL_OK)
    Protocol_HandleRxByte(&g_cmd_rx_uart2, ch);

  while (HAL_CAN_GetRxFifoFillLevel(&hcan1, CAN_RX_FIFO0) > 0U)
  {
    if (HAL_CAN_GetRxMessage(&hcan1, CAN_RX_FIFO0, &rx_header, rx_data) == HAL_OK)
      Protocol_HandleCanFrame(&rx_header, rx_data);
  }
}

static void App_TaskStep(void)
{
  uint32_t now = HAL_GetTick();

  /* During UART upgrade transfer, suppress periodic telemetry spam so the
   * command channel can sustain long UPG_DATA lines reliably. */
  if (g_upg_state == UPG_STATE_RECEIVING)
    return;

  if ((now - g_last_sample_tick) < g_sample_period_ms)
    return;

  g_last_sample_tick = now;

  float t = 0.0f, h = 0.0f;
  if (!g_sim_mode && Sensor_Read(&t, &h) == HAL_OK)
  {
    printf("TEMP=%.2fC RH=%.2f%% (type=%d bus=%s)\r\n", t, h, g_sensor_type, g_sensor_bus);
  }
  else
  {
    if (!g_sim_mode)
    {
      printf("SENSOR READ ERROR (bus=%s addr=%s), switch to SIM_MODE\r\n", g_sensor_bus, g_sensor_addr ? "ok" : "none");
      g_sim_mode = 1;
    }

    g_sim_t += 0.15f;
    if (g_sim_t > 30.0f) g_sim_t = 24.0f;
    g_sim_h += 0.30f;
    if (g_sim_h > 70.0f) g_sim_h = 45.0f;

    t = g_sim_t;
    h = g_sim_h;
    printf("SIM TEMP=%.2fC RH=%.2f%%\r\n", t, h);
  }

  Protocol_PrintFrameHex(0x01, (int16_t)(t * 100.0f), (uint16_t)(h * 100.0f));

  if (t >= g_temp_alarm_th_c || h >= g_hum_alarm_th_rh)
  {
    printf("ALARM %s%s T=%.2fC RH=%.2f%% (THR T=%.2f H=%.2f)\r\n",
           (t >= g_temp_alarm_th_c) ? "T" : "",
           (h >= g_hum_alarm_th_rh) ? "H" : "",
           t, h, g_temp_alarm_th_c, g_hum_alarm_th_rh);
    Protocol_PrintFrameHex(0xA1, (int16_t)(t * 100.0f), (uint16_t)(h * 100.0f));
  }

  if (VL53L0X_ReadDistanceMm(&g_sim_dist_mm) == HAL_OK && INA219_ReadCurrentMa(&g_sim_curr_ma) == HAL_OK)
  {
    printf("REAL2 DIST=%umm CUR=%umA\r\n", g_sim_dist_mm, g_sim_curr_ma);
  }
  else
  {
    g_sim_dist_mm = (g_sim_dist_mm > 120) ? (uint16_t)(g_sim_dist_mm - 35) : 1300;
    g_sim_curr_ma = (g_sim_curr_ma < 1700) ? (uint16_t)(g_sim_curr_ma + 22) : 320;
    printf("SIM2 DIST=%umm CUR=%umA\r\n", g_sim_dist_mm, g_sim_curr_ma);
  }
  Protocol_PrintFrameHex(0x02, (int16_t)g_sim_dist_mm, g_sim_curr_ma);

  if (g_sim_dist_mm <= g_dist_alarm_th_mm || g_sim_curr_ma >= g_curr_alarm_th_ma)
  {
    printf("ALARM2 %s%s DIST=%umm CUR=%umA (THR D=%u I=%u)\r\n",
           (g_sim_dist_mm <= g_dist_alarm_th_mm) ? "D" : "",
           (g_sim_curr_ma >= g_curr_alarm_th_ma) ? "I" : "",
           g_sim_dist_mm, g_sim_curr_ma, g_dist_alarm_th_mm, g_curr_alarm_th_ma);
    Protocol_PrintFrameHex(0xA2, (int16_t)g_sim_dist_mm, g_sim_curr_ma);
  }
}

static void I2C_PrintScan(I2C_HandleTypeDef *hi2c, const char *bus_name)
{
  uint8_t found = 0;

  printf("%s SCAN START\r\n", bus_name);
  for (uint16_t addr7 = 1; addr7 < 0x7F; addr7++)
  {
    uint16_t addr8 = (uint16_t)(addr7 << 1);
    if (HAL_I2C_IsDeviceReady(hi2c, addr8, 2, 5) == HAL_OK)
    {
      printf("%s DEV: 0x%02X\r\n", bus_name, addr7);
      found = 1;
    }
  }
  if (!found)
    printf("%s DEV: NONE\r\n", bus_name);
  printf("%s SCAN END\r\n", bus_name);
}

static void I2C_PrintScanAll(void)
{
  I2C_PrintScan(&hi2c1, "I2C1(PB6/PB7)");
  I2C_PrintScan(&hi2c2, "I2C2(PB10/PB11)");
}

static void Sensor_Detect(void)
{
  g_sensor_addr = 0;
  g_sensor_type = SENSOR_NONE;
  g_sensor_i2c = NULL;
  g_sensor_bus = "none";
  g_vl53_i2c = NULL;
  g_ina219_i2c = NULL;
  g_vl53_ok = 0U;
  g_ina219_ok = 0U;

  typedef struct
  {
    I2C_HandleTypeDef *hi2c;
    const char *name;
  } i2c_bus_t;

  i2c_bus_t buses[] = {
    {&hi2c1, "I2C1(PB6/PB7)"},
    {&hi2c2, "I2C2(PB10/PB11)"},
  };

  for (uint32_t i = 0; i < (sizeof(buses) / sizeof(buses[0])); i++)
  {
    I2C_HandleTypeDef *hi2c = buses[i].hi2c;
    const char *name = buses[i].name;

    if (HAL_I2C_IsDeviceReady(hi2c, SHT30_ADDR_44, 2, 30) == HAL_OK)
    {
      g_sensor_addr = SHT30_ADDR_44;
      g_sensor_type = SENSOR_SHT3X;
      g_sensor_i2c = hi2c;
      g_sensor_bus = name;
      break;
    }

    if (HAL_I2C_IsDeviceReady(hi2c, SHT30_ADDR_45, 2, 30) == HAL_OK)
    {
      g_sensor_addr = SHT30_ADDR_45;
      g_sensor_type = SENSOR_SHT3X;
      g_sensor_i2c = hi2c;
      g_sensor_bus = name;
      break;
    }
  }

  /* Distance + current channels default on I2C2 (PB10/PB11). */
  if (HAL_I2C_IsDeviceReady(&hi2c2, VL53L0X_ADDR, 2, 30) == HAL_OK)
  {
    g_vl53_i2c = &hi2c2;
    g_vl53_ok = 1U;
  }
  if (HAL_I2C_IsDeviceReady(&hi2c2, INA219_ADDR, 2, 30) == HAL_OK)
  {
    uint8_t cal_reg = 0x05;
    uint8_t cal_val[2] = {0x10, 0x00};
    g_ina219_i2c = &hi2c2;
    g_ina219_ok = 1U;
    (void)HAL_I2C_Mem_Write(g_ina219_i2c, INA219_ADDR, cal_reg, I2C_MEMADD_SIZE_8BIT, cal_val, 2, I2C_IO_TIMEOUT_MS);
  }
}

static HAL_StatusTypeDef Sensor_Read(float *temp_c, float *hum_rh)
{
  if (g_sensor_addr == 0 || g_sensor_type == SENSOR_NONE)
    Sensor_Detect();

  if (g_sensor_addr == 0 || g_sensor_type == SENSOR_NONE || g_sensor_i2c == NULL)
    return HAL_ERROR;

  if (g_sensor_type == SENSOR_SHT3X)
  {
    uint8_t cmd[2] = {0x2C, 0x06};
    uint8_t rx[6];

    if (HAL_I2C_Master_Transmit(g_sensor_i2c, g_sensor_addr, cmd, 2, I2C_IO_TIMEOUT_MS) != HAL_OK)
      return HAL_ERROR;

    HAL_Delay(20);

    if (HAL_I2C_Master_Receive(g_sensor_i2c, g_sensor_addr, rx, 6, I2C_IO_TIMEOUT_MS) != HAL_OK)
      return HAL_ERROR;

    uint16_t raw_t = ((uint16_t)rx[0] << 8) | rx[1];
    uint16_t raw_h = ((uint16_t)rx[3] << 8) | rx[4];

    *temp_c = -45.0f + 175.0f * ((float)raw_t / 65535.0f);
    *hum_rh = 100.0f * ((float)raw_h / 65535.0f);
    return HAL_OK;
  }

  return HAL_ERROR;
}

static HAL_StatusTypeDef VL53L0X_ReadDistanceMm(uint16_t *dist_mm)
{
  uint8_t reg = 0;
  uint8_t status = 0;
  uint8_t out[2] = {0};
  uint8_t start_cmd = 0x01;
  uint8_t clr[2] = {0x0B, 0x01};

  if (dist_mm == NULL || g_vl53_i2c == NULL || g_vl53_ok == 0U)
    return HAL_ERROR;

  /* Start a single ranging cycle. */
  reg = 0x00;
  if (HAL_I2C_Mem_Write(g_vl53_i2c, VL53L0X_ADDR, reg, I2C_MEMADD_SIZE_8BIT, &start_cmd, 1, I2C_IO_TIMEOUT_MS) != HAL_OK)
    return HAL_ERROR;

  for (uint8_t i = 0; i < 20U; i++)
  {
    reg = 0x13;
    if (HAL_I2C_Mem_Read(g_vl53_i2c, VL53L0X_ADDR, reg, I2C_MEMADD_SIZE_8BIT, &status, 1, I2C_IO_TIMEOUT_MS) != HAL_OK)
      return HAL_ERROR;
    if ((status & 0x07U) != 0U)
      break;
    HAL_Delay(2);
  }

  reg = 0x1E;
  if (HAL_I2C_Mem_Read(g_vl53_i2c, VL53L0X_ADDR, reg, I2C_MEMADD_SIZE_8BIT, out, 2, I2C_IO_TIMEOUT_MS) != HAL_OK)
    return HAL_ERROR;

  *dist_mm = ((uint16_t)out[0] << 8) | out[1];
  if (*dist_mm == 0U || *dist_mm > 4000U)
    return HAL_ERROR;

  /* Clear interrupt status. */
  if (HAL_I2C_Master_Transmit(g_vl53_i2c, VL53L0X_ADDR, clr, 2, I2C_IO_TIMEOUT_MS) != HAL_OK)
    return HAL_ERROR;
  return HAL_OK;
}

static HAL_StatusTypeDef INA219_ReadCurrentMa(uint16_t *curr_ma)
{
  uint8_t reg = 0x04;
  uint8_t raw[2] = {0};
  int16_t current_raw = 0;

  if (curr_ma == NULL || g_ina219_i2c == NULL || g_ina219_ok == 0U)
    return HAL_ERROR;

  if (HAL_I2C_Mem_Read(g_ina219_i2c, INA219_ADDR, reg, I2C_MEMADD_SIZE_8BIT, raw, 2, I2C_IO_TIMEOUT_MS) != HAL_OK)
    return HAL_ERROR;

  current_raw = (int16_t)(((uint16_t)raw[0] << 8) | raw[1]);
  if (current_raw < 0)
    current_raw = (int16_t)(-current_raw);

  /* Conservative conversion for the default calibration profile. */
  *curr_ma = (uint16_t)((uint16_t)current_raw / 10U);
  if (*curr_ma > 6000U)
    return HAL_ERROR;
  return HAL_OK;
}

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_I2C1_Init();
  MX_I2C2_Init();
  MX_SPI1_Init();
  MX_CAN1_Init();
  MX_USART1_UART_Init();
  MX_USART2_UART_Init();
  /* USER CODE BEGIN 2 */
  printf("BOOT_V3_DUAL_I2C_SCAN\r\n");
  if (HAL_CAN_Start(&hcan1) == HAL_OK)
    printf("CAN_READY:id_rx=0x%03X,id_tx=0x%03X\r\n", CAN_HOST_TO_DEV_STDID, CAN_DEV_TO_HOST_STDID);
  else
    printf("CAN_NOT_READY (check PA11/PA12 + transceiver)\r\n");
  if (W25_Init() == HAL_OK)
  {
    printf("W25_READY:id=0x%06lX%s\r\n",
           (unsigned long)g_w25_jedec_id,
           (g_w25_jedec_id == W25_JEDEC_ID_W25Q128) ? "" : " (NON-W25Q128)");
    Boot_LoadFromW25();
  }
  else
  {
    printf("W25_NOT_FOUND (check PA5/PA6/PA7 + PB12-CS + VCC/GND)\r\n");
  }
  I2C_PrintScanAll();
  Sensor_Detect();
  if (g_sensor_type == SENSOR_SHT3X && g_sensor_addr == SHT30_ADDR_44)
    printf("SHT3X DETECTED: 0x44 on %s\r\n", g_sensor_bus);
  else if (g_sensor_type == SENSOR_SHT3X && g_sensor_addr == SHT30_ADDR_45)
    printf("SHT3X DETECTED: 0x45 on %s\r\n", g_sensor_bus);
  else
  {
    g_sim_mode = 1;
    printf("SHT3X NOT FOUND (need addr 0x44/0x45; check PB6/PB7 or PB10/PB11, plus VCC/GND)\r\n");
    printf("SIM_MODE=ON (using virtual temp/humidity)\r\n");
  }
  if (g_vl53_ok)
    printf("VL53L0X DETECTED: 0x29 on I2C2(PB10/PB11)\r\n");
  else
    printf("VL53L0X NOT FOUND on I2C2(PB10/PB11), DIST channel uses fallback profile\r\n");
  if (g_ina219_ok)
    printf("INA219 DETECTED: 0x40 on I2C2(PB10/PB11)\r\n");
  else
    printf("INA219 NOT FOUND on I2C2(PB10/PB11), CUR channel uses fallback profile\r\n");
  printf("CMD: GET_PERIOD / SET_PERIOD <100-5000>\r\n");
  printf("CMD: GET_THR / SET_THR_T <0-80> / SET_THR_H <0-100>\r\n");
  printf("CMD: GET_THR2 / SET_THR_D <50-4000> / SET_THR_I <100-5000>\r\n");
  printf("CMD: GET_VER / GET_CAP / GET_BOOTSTATE / UPG_STATUS / UPG_ABORT\r\n");
  printf("CMD: UPG_BEGIN <ver> <size> <crc32> / UPG_DATA <off> <hex> <crc32>\r\n");
  printf("CMD: UPG_END / UPG_ACTIVATE / UPG_CONFIRM / UPG_FAIL_ONCE\r\n");
  printf("CMD: FLASH_ID(GET_FLASH) / BOOT_SAVE / BOOT_LOAD\r\n");
  printf("CAN_TUNNEL: id_rx=0x%03X id_tx=0x%03X pkt=SEG/EOM/ACK/NACK\r\n", CAN_HOST_TO_DEV_STDID, CAN_DEV_TO_HOST_STDID);
  Upg_ResetSession();
  Boot_PrintState();
  g_last_sample_tick = HAL_GetTick();

  /* USER CODE END 2 */

  /* Init scheduler */
  osKernelInitialize();

  /* USER CODE BEGIN RTOS_MUTEX */
  /* add mutexes, ... */
  /* USER CODE END RTOS_MUTEX */

  /* USER CODE BEGIN RTOS_SEMAPHORES */
  /* add semaphores, ... */
  /* USER CODE END RTOS_SEMAPHORES */

  /* USER CODE BEGIN RTOS_TIMERS */
  /* start timers, add new ones, ... */
  /* USER CODE END RTOS_TIMERS */

  /* USER CODE BEGIN RTOS_QUEUES */
  /* add queues, ... */
  /* USER CODE END RTOS_QUEUES */

  /* Create the thread(s) */
  /* creation of defaultTask */
  defaultTaskHandle = osThreadNew(StartDefaultTask, NULL, &defaultTask_attributes);
  if (defaultTaskHandle == NULL)
  {
    printf("RTOS ERR: create defaultTask failed\r\n");
    Error_Handler();
  }

  /* USER CODE BEGIN RTOS_THREADS */
  sampleTaskHandle = osThreadNew(StartSampleTask, NULL, &sampleTask_attributes);
  if (sampleTaskHandle == NULL)
  {
    printf("RTOS ERR: create sampleTask failed\r\n");
    Error_Handler();
  }
  cmdTaskHandle = osThreadNew(StartCmdTask, NULL, &cmdTask_attributes);
  if (cmdTaskHandle == NULL)
  {
    printf("RTOS ERR: create cmdTask failed\r\n");
    Error_Handler();
  }
  /* USER CODE END RTOS_THREADS */

  /* USER CODE BEGIN RTOS_EVENTS */
  /* add events, ... */
  /* USER CODE END RTOS_EVENTS */

  /* Start scheduler */
  osKernelStart();

  /* We should never get here as control is now taken by the scheduler */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
    HAL_Delay(1000);
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSI;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.HSICalibrationValue = RCC_HSICALIBRATION_DEFAULT;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_NONE;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_HSI;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_0) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief I2C1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_I2C1_Init(void)
{

  /* USER CODE BEGIN I2C1_Init 0 */

  /* USER CODE END I2C1_Init 0 */

  /* USER CODE BEGIN I2C1_Init 1 */

  /* USER CODE END I2C1_Init 1 */
  hi2c1.Instance = I2C1;
  hi2c1.Init.ClockSpeed = 100000;
  hi2c1.Init.DutyCycle = I2C_DUTYCYCLE_2;
  hi2c1.Init.OwnAddress1 = 0;
  hi2c1.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c1.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c1.Init.OwnAddress2 = 0;
  hi2c1.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c1.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN I2C1_Init 2 */

  /* USER CODE END I2C1_Init 2 */

}

/**
  * @brief I2C2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_I2C2_Init(void)
{

  /* USER CODE BEGIN I2C2_Init 0 */

  /* USER CODE END I2C2_Init 0 */

  /* USER CODE BEGIN I2C2_Init 1 */

  /* USER CODE END I2C2_Init 1 */
  hi2c2.Instance = I2C2;
  hi2c2.Init.ClockSpeed = 100000;
  hi2c2.Init.DutyCycle = I2C_DUTYCYCLE_2;
  hi2c2.Init.OwnAddress1 = 0;
  hi2c2.Init.AddressingMode = I2C_ADDRESSINGMODE_7BIT;
  hi2c2.Init.DualAddressMode = I2C_DUALADDRESS_DISABLE;
  hi2c2.Init.OwnAddress2 = 0;
  hi2c2.Init.GeneralCallMode = I2C_GENERALCALL_DISABLE;
  hi2c2.Init.NoStretchMode = I2C_NOSTRETCH_DISABLE;
  if (HAL_I2C_Init(&hi2c2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN I2C2_Init 2 */

  /* USER CODE END I2C2_Init 2 */

}

/**
  * @brief SPI1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_SPI1_Init(void)
{

  /* USER CODE BEGIN SPI1_Init 0 */

  /* USER CODE END SPI1_Init 0 */

  /* USER CODE BEGIN SPI1_Init 1 */

  /* USER CODE END SPI1_Init 1 */
  hspi1.Instance = SPI1;
  hspi1.Init.Mode = SPI_MODE_MASTER;
  hspi1.Init.Direction = SPI_DIRECTION_2LINES;
  hspi1.Init.DataSize = SPI_DATASIZE_8BIT;
  hspi1.Init.CLKPolarity = SPI_POLARITY_LOW;
  hspi1.Init.CLKPhase = SPI_PHASE_1EDGE;
  hspi1.Init.NSS = SPI_NSS_SOFT;
  hspi1.Init.BaudRatePrescaler = SPI_BAUDRATEPRESCALER_16;
  hspi1.Init.FirstBit = SPI_FIRSTBIT_MSB;
  hspi1.Init.TIMode = SPI_TIMODE_DISABLE;
  hspi1.Init.CRCCalculation = SPI_CRCCALCULATION_DISABLE;
  hspi1.Init.CRCPolynomial = 10;
  if (HAL_SPI_Init(&hspi1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN SPI1_Init 2 */

  /* USER CODE END SPI1_Init 2 */

}

/**
  * @brief CAN1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_CAN1_Init(void)
{
  CAN_FilterTypeDef filter = {0};

  hcan1.Instance = CAN1;
  hcan1.Init.Prescaler = 6;
  hcan1.Init.Mode = CAN_MODE_NORMAL;
  hcan1.Init.SyncJumpWidth = CAN_SJW_1TQ;
  hcan1.Init.TimeSeg1 = CAN_BS1_13TQ;
  hcan1.Init.TimeSeg2 = CAN_BS2_2TQ;
  hcan1.Init.TimeTriggeredMode = DISABLE;
  hcan1.Init.AutoBusOff = ENABLE;
  hcan1.Init.AutoWakeUp = DISABLE;
  hcan1.Init.AutoRetransmission = ENABLE;
  hcan1.Init.ReceiveFifoLocked = DISABLE;
  hcan1.Init.TransmitFifoPriority = DISABLE;
  if (HAL_CAN_Init(&hcan1) != HAL_OK)
  {
    Error_Handler();
  }

  /* Accept all IDs in FIFO0 and filter by StdId in software. */
  filter.FilterBank = 0;
  filter.FilterMode = CAN_FILTERMODE_IDMASK;
  filter.FilterScale = CAN_FILTERSCALE_32BIT;
  filter.FilterIdHigh = 0x0000;
  filter.FilterIdLow = 0x0000;
  filter.FilterMaskIdHigh = 0x0000;
  filter.FilterMaskIdLow = 0x0000;
  filter.FilterFIFOAssignment = CAN_FILTER_FIFO0;
  filter.FilterActivation = ENABLE;
  filter.SlaveStartFilterBank = 14;
  if (HAL_CAN_ConfigFilter(&hcan1, &filter) != HAL_OK)
  {
    Error_Handler();
  }
}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
/**
  * @brief USART1 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART1_UART_Init(void)
{

  /* USER CODE BEGIN USART1_Init 0 */

  /* USER CODE END USART1_Init 0 */

  /* USER CODE BEGIN USART1_Init 1 */

  /* USER CODE END USART1_Init 1 */
  huart1.Instance = USART1;
  huart1.Init.BaudRate = 115200;
  huart1.Init.WordLength = UART_WORDLENGTH_8B;
  huart1.Init.StopBits = UART_STOPBITS_1;
  huart1.Init.Parity = UART_PARITY_NONE;
  huart1.Init.Mode = UART_MODE_TX_RX;
  huart1.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart1.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart1) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART1_Init 2 */

  /* USER CODE END USART1_Init 2 */

}

/**
  * @brief USART2 Initialization Function
  * @param None
  * @retval None
  */
static void MX_USART2_UART_Init(void)
{

  /* USER CODE BEGIN USART2_Init 0 */

  /* USER CODE END USART2_Init 0 */

  /* USER CODE BEGIN USART2_Init 1 */

  /* USER CODE END USART2_Init 1 */
  huart2.Instance = USART2;
  huart2.Init.BaudRate = 115200;
  huart2.Init.WordLength = UART_WORDLENGTH_8B;
  huart2.Init.StopBits = UART_STOPBITS_1;
  huart2.Init.Parity = UART_PARITY_NONE;
  huart2.Init.Mode = UART_MODE_TX_RX;
  huart2.Init.HwFlowCtl = UART_HWCONTROL_NONE;
  huart2.Init.OverSampling = UART_OVERSAMPLING_16;
  if (HAL_UART_Init(&huart2) != HAL_OK)
  {
    Error_Handler();
  }
  /* USER CODE BEGIN USART2_Init 2 */

  /* USER CODE END USART2_Init 2 */

}

/**
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();

  /* USER CODE BEGIN MX_GPIO_Init_2 */
  HAL_GPIO_WritePin(W25_CS_GPIO_Port, W25_CS_Pin, GPIO_PIN_SET);

  GPIO_InitStruct.Pin = W25_CS_Pin;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  HAL_GPIO_Init(W25_CS_GPIO_Port, &GPIO_InitStruct);

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */
void StartSampleTask(void *argument)
{
  for (;;)
  {
    App_TaskStep();
    osDelay(5);
  }
}

void StartCmdTask(void *argument)
{
  for (;;)
  {
    Protocol_PollRx();
    osDelay(2);
  }
}

/* USER CODE END 4 */

/* USER CODE BEGIN Header_StartDefaultTask */
/**
  * @brief  Function implementing the defaultTask thread.
  * @param  argument: Not used
  * @retval None
  */
/* USER CODE END Header_StartDefaultTask */
void StartDefaultTask(void *argument)
{
  /* USER CODE BEGIN 5 */
  /* Infinite loop */
  for(;;)
  {
    osDelay(1000);
  }
  /* USER CODE END 5 */
}

/**
  * @brief  Period elapsed callback in non blocking mode
  * @note   This function is called  when TIM6 interrupt took place, inside
  * HAL_TIM_IRQHandler(). It makes a direct call to HAL_IncTick() to increment
  * a global variable "uwTick" used as application time base.
  * @param  htim : TIM handle
  * @retval None
  */
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
  /* USER CODE BEGIN Callback 0 */

  /* USER CODE END Callback 0 */
  if (htim->Instance == TIM6)
  {
    HAL_IncTick();
  }
  /* USER CODE BEGIN Callback 1 */

  /* USER CODE END Callback 1 */
}

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}
#ifdef USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
