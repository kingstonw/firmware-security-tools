# 组件结构迁移清单

## ✅ 完成的工作

### 1. 目录结构创建
- [x] components/core/{src,include}
- [x] components/mqtt/{src,include}
- [x] components/network/{src,include}
- [x] components/communication/{src,include}
- [x] components/display/{src,include}
- [x] components/input/{src,include}
- [x] components/ota/{src,include}
- [x] components/device/{src,include}

### 2. 源文件迁移
- [x] mqtt_task.cpp → components/mqtt/src/
- [x] wifi_task.cpp → components/network/src/
- [x] uart_tx_task.cpp → components/communication/src/
- [x] uart_rx_task.cpp → components/communication/src/
- [x] input_task.cpp → components/input/src/
- [x] screen_task.cpp → components/display/src/
- [x] ota_management_task.cpp → components/ota/src/
- [x] ota_flash_task.cpp → components/ota/src/
- [x] set_parameters_task.cpp → components/device/src/
- [x] queues.cpp → components/core/src/
- [x] wifi_{strong,medium,weak,off}.c → components/network/src/

### 3. 头文件迁移
- [x] queues.hpp → components/core/include/
- [x] button.hpp → components/input/include/
- [x] nvs_handle.hpp → components/device/include/
- [x] screen_task.h → components/display/include/
- [x] commons.hpp → main/include/
- [x] mqtt_config.h → main/include/

### 4. CMakeLists.txt配置
- [x] components/core/CMakeLists.txt
- [x] components/mqtt/CMakeLists.txt
- [x] components/network/CMakeLists.txt
- [x] components/communication/CMakeLists.txt
- [x] components/display/CMakeLists.txt
- [x] components/input/CMakeLists.txt
- [x] components/ota/CMakeLists.txt
- [x] components/device/CMakeLists.txt
- [x] main/CMakeLists.txt (重写)

### 5. idf_component.yml配置
- [x] 为所有8个新component创建idf_component.yml

### 6. 任务声明头文件
- [x] components/mqtt/include/mqtt_task.h
- [x] components/network/include/wifi_task.h
- [x] components/communication/include/uart_task.h
- [x] components/display/include/screen_task.h
- [x] components/input/include/input_task.h
- [x] components/ota/include/ota_task.h
- [x] components/device/include/device_task.h

### 7. Include路径更新
- [x] mqtt_task.cpp: components/queues.hpp → queues.hpp
- [x] uart_tx_task.cpp: components/queues.hpp → queues.hpp
- [x] uart_rx_task.cpp: components/queues.hpp → queues.hpp
- [x] input_task.cpp: components/queues.hpp → queues.hpp
- [x] input_task.cpp: tasks/screen_task.h → screen_task.h
- [x] input_task.cpp: components/button.hpp → button.hpp
- [x] screen_task.cpp: components/queues.hpp → queues.hpp
- [x] ota_management_task.cpp: components/queues.hpp → queues.hpp
- [x] ota_flash_task.cpp: components/queues.hpp → queues.hpp
- [x] uart_rx_task.cpp: components/nvs_handle.hpp → nvs_handle.hpp
- [x] main.cpp: components/queues.hpp → queues.hpp

### 8. 依赖关系配置
- [x] communication REQUIRES: device (for nvs_handle.hpp)
- [x] 所有component REQUIRES: core (for queues.hpp)
- [x] main REQUIRES: core, mqtt, network, communication, display, input, ota, device

### 9. 旧文件清理
- [x] 删除 main/tasks/ 中的所有 .cpp 文件
- [x] 删除 main/components/ 中的所有 .cpp 和 .hpp 文件
- [x] 保期 main/tasks/tasks.hpp（汇总声明文件）

## 🔍 需要验证的项目

### 编译测试
```bash
cd /Users/kingstonw/FCS_ws/WatusiPanel-V3
idf.py set-target esp32s3
idf.py build
```

### 预期编译结果
如果成功，应该看到：
- 所有8个component编译完成
- no linker errors
- main component链接所有依赖

### 可能的问题

1. **missing include '*.h'**
   - 原因: include路径没有更新
   - 解决: 检查CMakeLists.txt中INCLUDE_DIRS和PRIV_INCLUDE_DIRS配置

2. **undefined reference to 'xxx_task'**
   - 原因: 某个component没有加入main的REQUIRES
   - 解决: 在main/CMakeLists.txt中添加missing component

3. **circular dependency**
   - 原因: 两个component互相依赖
   - 解决: 提取公共部分到core或第三个component

## 📋 后续步骤

1. [ ] 执行编译验证
2. [ ] 刷写设备并测试功能
3. [ ] 更新CI/CD配置
4. [ ] 清理旧的main/{tasks,components}目录（保留原始备份）
5. [ ] 更新项目文档
6. [ ] 添加component单元测试

## 💡 最佳实践

- 保留原有的main/{tasks,components}直到完全验证新结构正常工作
- 逐个component进行单元测试
- 使用`idf.py build --verbose`获取详细编译信息
- 监控二进制文件大小，优化内存使用
