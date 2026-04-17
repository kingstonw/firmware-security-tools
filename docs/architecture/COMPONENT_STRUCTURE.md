# WatusiPanel-V3 模块化组件结构

## 项目架构重构完成

### 总体结构

```
components/
├── core/                    # 核心基础设施
│   ├── CMakeLists.txt
│   ├── idf_component.yml
│   ├── src/
│   │   └── queues.cpp
│   └── include/
│       └── queues.hpp       # FreeRTOS 队列管理
│
├── network/                 # WiFi网络管理
│   ├── CMakeLists.txt
│   ├── idf_component.yml
│   ├── src/
│   │   ├── wifi_task.cpp
│   │   ├── wifi_strong.c
│   │   ├── wifi_medium.c
│   │   ├── wifi_weak.c
│   │   └── wifi_off.c
│   └── include/
│       └── wifi_task.h
│
├── communication/           # UART串口通信
│   ├── CMakeLists.txt
│   ├── idf_component.yml
│   ├── src/
│   │   ├── uart_tx_task.cpp
│   │   └── uart_rx_task.cpp
│   └── include/
│       └── uart_task.h
│
├── mqtt/                    # MQTT消息代理
│   ├── CMakeLists.txt
│   ├── idf_component.yml
│   ├── src/
│   │   └── mqtt_task.cpp
│   └── include/
│       └── mqtt_task.h
│
├── display/                 # 屏幕显示UI
│   ├── CMakeLists.txt
│   ├── idf_component.yml
│   ├── src/
│   │   └── screen_task.cpp
│   └── include/
│       ├── screen_task.h
│
├── input/                   # 输入处理器（按键）
│   ├── CMakeLists.txt
│   ├── idf_component.yml
│   ├── src/
│   │   └── input_task.cpp
│   └── include/
│       ├── input_task.h
│       └── button.hpp
│
├── ota/                     # OTA固件更新
│   ├── CMakeLists.txt
│   ├── idf_component.yml
│   ├── src/
│   │   ├── ota_management_task.cpp
│   │   └── ota_flash_task.cpp
│   └── include/
│       └── ota_task.h
│
├── device/                  # 设备配置管理
│   ├── CMakeLists.txt
│   ├── idf_component.yml
│   ├── src/
│   │   └── set_parameters_task.cpp
│   └── include/
│       ├── device_task.h
│       └── nvs_handle.hpp    # NVS存储处理
│
├── lvgl/                    # LVGL UI库

main/                       # 主程序入口
├── CMakeLists.txt         # 依赖所有component
├── idf_component.yml
├── main.cpp
├── commons.cpp
├── commons.hpp
├── include/
│   ├── commons.hpp
│   ├── mqtt_config.h
│   ├── ota_protocol.h
│   └── aws_iot_config.h
├── tasks/
│   └── tasks.hpp          # 所有任务声明汇总
├── certs/                 # SSL证书
└── images/                # UI资源
```

## 组件依赖关系

```
                    ┌────────────────┐
                    │     main       │
                    └────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼────┐    ┌──────▼──────┐    ┌────▼────┐
    │   core  │◄───┤ mqtt network │    │ display │
    └────┬────┘    │ communication│    └────┬────┘
         │         │ input ota    │         │
         │         │ device       │         │
         └─────────┴──────────────┴─────────┘
```

## ESP-IDF 构建机制

每个component都遵循ESP-IDF标准结构：
- `CMakeLists.txt` - 定义源文件、include目录、依赖关系
- `idf_component.yml` - component元数据和版本信息
- `src/` - 源代码文件
- `include/` - 公开头文件

## include路径说明

### 跨component引用
- 组件通过`REQUIRES`声明依赖
- 被依赖component的`include/`目录自动对外公开
- 例：`communication`需要`device`，通过`#include "nvs_handle.hpp"`访问

### 对主程序(main)的引用
- main在`main/include/`包含了共享头文件
- 其他component通过`PRIV_INCLUDE_DIRS "../../../main/include"`引用
- 这避免了对main component的显式依赖

## 编译命令

```bash
# 设置目标芯片
idf.py set-target esp32s3

# 标准编译
idf.py build

# 2M PSRAM配置
./2m_build.sh

# 8M PSRAM配置
./8m_build.sh

# 编译并烧写
idf.py flash

# 监控串口输出
idf.py monitor
```

## 代码迁移要点

1. **include路径规范化**
   - `components/queues.hpp` → `queues.hpp`
   - `components/button.hpp` → `button.hpp`
   - `tasks/screen_task.h` → `screen_task.h`（通过PRIV_INCLUDE_DIRS）

2. **依赖关系明确化**
   - component的CMakeLists.txt明确声明所有外部依赖
   - 支持条件编译和可选组件

3. **模块独立性**
   - 每个组件可独立测试和重用
   - 减少全局变量和隐藏依赖

## 优势

✓ **模块化** - 业务逻辑清晰分离  
✓ **可维护性** - 易于定位和修改特定功能  
✓ **可测试性** - component可独立单元测试  
✓ **可重用性** - component可复用到其他项目  
✓ **构建效率** - 支持增量编译和依赖优化
