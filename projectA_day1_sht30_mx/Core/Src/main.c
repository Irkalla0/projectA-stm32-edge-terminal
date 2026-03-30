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

typedef enum
{
  SENSOR_NONE = 0,
  SENSOR_SHT3X
} sensor_type_t;

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/
I2C_HandleTypeDef hi2c1;
I2C_HandleTypeDef hi2c2;

UART_HandleTypeDef huart1;

/* Definitions for defaultTask */
osThreadId_t defaultTaskHandle;
const osThreadAttr_t defaultTask_attributes = {
  .name = "defaultTask",
  .stack_size = 128 * 4,
  .priority = (osPriority_t) osPriorityNormal,
};
/* USER CODE BEGIN PV */
static uint16_t g_sensor_addr = 0;
static sensor_type_t g_sensor_type = SENSOR_NONE;
static I2C_HandleTypeDef *g_sensor_i2c = NULL;
static const char *g_sensor_bus = "none";
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
static char g_cmd_buf[64];
static uint8_t g_cmd_len = 0;
static uint32_t g_last_sample_tick = 0;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
static void MX_GPIO_Init(void);
static void MX_I2C1_Init(void);
static void MX_I2C2_Init(void);
static void MX_USART1_UART_Init(void);
void StartDefaultTask(void *argument);

/* USER CODE BEGIN PFP */
static void I2C_PrintScan(I2C_HandleTypeDef *hi2c, const char *bus_name);
static void I2C_PrintScanAll(void);
static void Sensor_Detect(void);
static HAL_StatusTypeDef Sensor_Read(float *temp_c, float *hum_rh);
static uint16_t CRC16_Modbus(const uint8_t *data, uint16_t len);
static void Protocol_PrintFrameHex(uint8_t cmd, int16_t temp_centi, uint16_t hum_centi);
static void Protocol_ProcessCommand(const char *cmd);
static void Protocol_HandleRxByte(uint8_t ch);
static void Protocol_PollRx(void);
static void App_TaskStep(void);

/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */
int __io_putchar(int ch)
{
  HAL_UART_Transmit(&huart1, (uint8_t *)&ch, 1, HAL_MAX_DELAY);
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
  char cmd_trim[64];
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

  if (cmd_trim[0] != '\0')
    printf("CMD_ERR:%s\r\n", cmd_trim);
}

static void Protocol_HandleRxByte(uint8_t ch)
{
  if (ch == '\r')
    return;

  if (ch == '\n')
  {
    g_cmd_buf[g_cmd_len] = '\0';
    Protocol_ProcessCommand(g_cmd_buf);
    g_cmd_len = 0;
    return;
  }

  if (g_cmd_len < (sizeof(g_cmd_buf) - 1))
  {
    g_cmd_buf[g_cmd_len++] = (char)ch;
  }
  else
  {
    g_cmd_len = 0;
  }
}

static void Protocol_PollRx(void)
{
  uint8_t ch = 0;
  while (HAL_UART_Receive(&huart1, &ch, 1, 0) == HAL_OK)
    Protocol_HandleRxByte(ch);
}

static void App_TaskStep(void)
{
  uint32_t now = HAL_GetTick();
  Protocol_PollRx();

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

  g_sim_dist_mm = (g_sim_dist_mm > 120) ? (uint16_t)(g_sim_dist_mm - 35) : 1300;
  g_sim_curr_ma = (g_sim_curr_ma < 1700) ? (uint16_t)(g_sim_curr_ma + 22) : 320;
  printf("SIM2 DIST=%umm CUR=%umA\r\n", g_sim_dist_mm, g_sim_curr_ma);
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
      return;
    }

    if (HAL_I2C_IsDeviceReady(hi2c, SHT30_ADDR_45, 2, 30) == HAL_OK)
    {
      g_sensor_addr = SHT30_ADDR_45;
      g_sensor_type = SENSOR_SHT3X;
      g_sensor_i2c = hi2c;
      g_sensor_bus = name;
      return;
    }
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

    if (HAL_I2C_Master_Transmit(g_sensor_i2c, g_sensor_addr, cmd, 2, HAL_MAX_DELAY) != HAL_OK)
      return HAL_ERROR;

    HAL_Delay(20);

    if (HAL_I2C_Master_Receive(g_sensor_i2c, g_sensor_addr, rx, 6, HAL_MAX_DELAY) != HAL_OK)
      return HAL_ERROR;

    uint16_t raw_t = ((uint16_t)rx[0] << 8) | rx[1];
    uint16_t raw_h = ((uint16_t)rx[3] << 8) | rx[4];

    *temp_c = -45.0f + 175.0f * ((float)raw_t / 65535.0f);
    *hum_rh = 100.0f * ((float)raw_h / 65535.0f);
    return HAL_OK;
  }

  return HAL_ERROR;
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
  MX_USART1_UART_Init();
  /* USER CODE BEGIN 2 */
  printf("BOOT_V3_DUAL_I2C_SCAN\r\n");
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
  printf("CMD: GET_PERIOD / SET_PERIOD <100-5000>\r\n");
  printf("CMD: GET_THR / SET_THR_T <0-80> / SET_THR_H <0-100>\r\n");
  printf("CMD: GET_THR2 / SET_THR_D <50-4000> / SET_THR_I <100-5000>\r\n");
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

  /* USER CODE BEGIN RTOS_THREADS */
  /* add threads, ... */
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
  * @brief GPIO Initialization Function
  * @param None
  * @retval None
  */
static void MX_GPIO_Init(void)
{
  /* USER CODE BEGIN MX_GPIO_Init_1 */

  /* USER CODE END MX_GPIO_Init_1 */

  /* GPIO Ports Clock Enable */
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();

  /* USER CODE BEGIN MX_GPIO_Init_2 */

  /* USER CODE END MX_GPIO_Init_2 */
}

/* USER CODE BEGIN 4 */

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
    App_TaskStep();
    osDelay(5);
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
