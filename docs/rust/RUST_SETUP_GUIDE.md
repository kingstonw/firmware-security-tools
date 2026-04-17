# Rust 集成完整安装指南

## 步骤 1：安装 Rust 工具链

### 1.1 安装 Rust（如果还没有）

```bash
# 安装 Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 重新加载 shell 配置
source $HOME/.cargo/env

# 验证安装
rustc --version
cargo --version
```

### 1.2 安装 ESP-IDF Rust 工具链

```bash
# 安装 espup（ESP-IDF Rust 安装工具）
cargo install espup

# 安装 ESP-IDF Rust 工具链（这会下载工具链，可能需要几分钟）
espup install

# 设置环境变量（添加到 ~/.zshrc 或 ~/.bashrc）
echo 'source $HOME/.export-esp.sh' >> ~/.zshrc  # 或 ~/.bashrc
source $HOME/.export-esp.sh

# 验证安装
echo $ESP_IDF_VERSION  # 应该显示版本号
```

**注意**：如果 `espup install` 失败，可能需要先设置 ESP-IDF 环境：
```bash
# 如果你的 ESP-IDF 已经安装，设置路径
export ESP_IDF_PATH=/Users/kingstonw/esp/v6.0/esp-idf
espup install
```

## 步骤 2：创建 Rust 项目结构

### 2.1 创建 rust_tasks 文件夹

**位置**：在项目根目录（与 `main/` 同级）

```bash
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2
cargo new --lib rust_tasks
```

**目录结构**：
```
WatusiPanel-V2/
├── main/
│   ├── CMakeLists.txt
│   ├── main.cpp
│   └── ...
├── rust_tasks/          ← 新建的 Rust 项目
│   ├── Cargo.toml
│   ├── src/
│   │   └── lib.rs
│   └── target/          ← 构建输出（自动生成）
└── ...
```

### 2.2 配置 Cargo.toml

编辑 `rust_tasks/Cargo.toml`：

```toml
[package]
name = "rust_tasks"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["staticlib"]  # 生成静态库供 C 链接

[dependencies]
esp-idf-sys = { version = "0.36", features = ["binstart"] }
log = "0.4"

[profile.release]
opt-level = "z"      # 优化大小
lto = true          # 链接时优化
codegen-units = 1   # 更好的优化
```

### 2.3 创建最小 Rust 代码

编辑 `rust_tasks/src/lib.rs`：

```rust
#![no_std]  // 不使用标准库（嵌入式）

use esp_idf_sys::*;
use log::*;

// 最简单的测试函数
#[no_mangle]
pub extern "C" fn rust_test() {
    info!("🚀 Rust function called from C!");
}

// 按钮状态处理示例（混合架构）
#[no_mangle]
pub extern "C" fn rust_process_button_state(
    pressed: bool,
    duration_ms: u32,
) -> u32 {
    if pressed && duration_ms > 10000 {
        info!("Long press detected from Rust! Duration: {} ms", duration_ms);
        return 1;  // 返回事件类型
    }
    0  // 无事件
}
```

## 步骤 3：配置 ESP-IDF 构建系统

### 3.1 修改 main/CMakeLists.txt

在 `main/CMakeLists.txt` 的末尾添加：

```cmake
# ============================================
# Rust Tasks Integration
# ============================================

# 设置 Rust 项目路径
set(RUST_TASKS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../rust_tasks")
set(RUST_TARGET_DIR "${RUST_TASKS_DIR}/target")
set(RUST_TARGET "xtensa-esp32s3-espidf")  # 根据你的芯片调整
set(RUST_LIB "${RUST_TARGET_DIR}/${RUST_TARGET}/release/librust_tasks.a")

# 构建 Rust 库的自定义目标
add_custom_target(rust_tasks_build
    COMMAND ${CMAKE_COMMAND} -E env "CARGO_TARGET_DIR=${RUST_TARGET_DIR}" 
            cargo build --release 
            --manifest-path ${RUST_TASKS_DIR}/Cargo.toml
            --target ${RUST_TARGET}
    WORKING_DIRECTORY ${RUST_TASKS_DIR}
    COMMENT "Building Rust tasks library"
    VERBATIM
)

# 确保 Rust 库在链接前构建
add_dependencies(${COMPONENT_LIB} rust_tasks_build)

# 链接 Rust 静态库
target_link_libraries(${COMPONENT_LIB} 
    PRIVATE 
    ${RUST_LIB}
)

# 包含 Rust 头文件目录（如果需要）
target_include_directories(${COMPONENT_LIB} 
    PRIVATE 
    ${CMAKE_CURRENT_SOURCE_DIR}/../rust_tasks/include
)
```

### 3.2 创建 Rust 头文件（可选）

创建 `rust_tasks/include/rust_tasks.h`：

```c
#ifndef RUST_TASKS_H
#define RUST_TASKS_H

#ifdef __cplusplus
extern "C" {
#endif

// Rust 函数声明
void rust_test(void);
uint32_t rust_process_button_state(bool pressed, uint32_t duration_ms);

#ifdef __cplusplus
}
#endif

#endif // RUST_TASKS_H
```

## 步骤 4：在 C++ 中调用 Rust 函数

### 4.1 在 main.cpp 中添加测试代码

在 `main/main.cpp` 的 `app_main()` 函数中添加：

```cpp
// 在文件顶部添加
extern "C" {
    void rust_test();
    uint32_t rust_process_button_state(bool pressed, uint32_t duration_ms);
}

// 在 app_main() 中添加测试
void app_main() {
    // ... 其他初始化代码 ...
    
    // 测试 Rust 函数
    ESP_LOGI("MAIN", "Testing Rust integration...");
    rust_test();
    
    // ... 其他代码 ...
}
```

### 4.2 在 input_task 中使用（示例）

在 `main/tasks/input_task.cpp` 中：

```cpp
// 在文件顶部添加
extern "C" {
    uint32_t rust_process_button_state(bool pressed, uint32_t duration_ms);
}

// 在 input_task 函数中使用（测试用）
void input_task(void *pvParameters) {
    // ... 原有代码 ...
    
    // 测试：调用 Rust 函数
    bool test_pressed = true;
    uint32_t test_duration = 15000;
    uint32_t event = rust_process_button_state(test_pressed, test_duration);
    ESP_LOGI("INPUT", "Rust returned event: %u", event);
    
    // ... 原有代码 ...
}
```

## 步骤 5：配置 Rust 目标架构

### 5.1 添加 Rust 目标

```bash
# 进入 rust_tasks 目录
cd rust_tasks

# 添加 ESP32-S3 目标（根据你的芯片调整）
rustup target add xtensa-esp32s3-espidf

# 如果目标不存在，可能需要：
# rustup target list | grep esp
# 或者使用 espup 安装的目标
```

### 5.2 创建 .cargo/config.toml（可选）

创建 `rust_tasks/.cargo/config.toml`：

```toml
[build]
target = "xtensa-esp32s3-espidf"  # 默认目标

[target.xtensa-esp32s3-espidf]
runner = "espflash flash --monitor"  # 可选：直接烧录
```

## 步骤 6：构建和测试

### 6.1 首次构建 Rust 库

```bash
# 设置环境
source $HOME/.export-esp.sh

# 进入 rust_tasks 目录
cd rust_tasks

# 构建 Rust 库（首次构建可能需要 10-20 分钟）
cargo build --release --target xtensa-esp32s3-espidf

# 验证库文件已生成
ls -lh target/xtensa-esp32s3-espidf/release/librust_tasks.a
```

### 6.2 构建 ESP-IDF 项目

```bash
# 返回项目根目录
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2

# 构建 ESP-IDF 项目（会自动构建 Rust 库）
idf.py build

# 如果构建成功，烧录和监控
idf.py flash monitor
```

### 6.3 验证输出

在串口监视器中，你应该看到：
```
I (xxx) rust_tasks: 🚀 Rust function called from C!
I (xxx) rust_tasks: Long press detected from Rust! Duration: 15000 ms
```

## 步骤 7：目录结构总结

### 最终目录结构

```
WatusiPanel-V2/
├── main/
│   ├── CMakeLists.txt          ← 已修改（添加 Rust 构建）
│   ├── main.cpp                 ← 已修改（添加 Rust 调用）
│   ├── tasks/
│   │   ├── input_task.cpp       ← 可选：添加 Rust 调用
│   │   └── ...
│   └── ...
├── rust_tasks/                  ← 新建的 Rust 项目
│   ├── .cargo/
│   │   └── config.toml          ← 可选：Rust 配置
│   ├── include/
│   │   └── rust_tasks.h         ← 可选：C 头文件
│   ├── src/
│   │   └── lib.rs               ← Rust 代码
│   ├── Cargo.toml               ← Rust 项目配置
│   └── target/                   ← 构建输出（自动生成）
│       └── xtensa-esp32s3-espidf/
│           └── release/
│               └── librust_tasks.a  ← 生成的静态库
├── build/                        ← ESP-IDF 构建输出
└── ...
```

## 常见问题解决

### 问题 1：找不到 Rust 工具链

```bash
# 检查环境变量
echo $ESP_IDF_VERSION
echo $CARGO_HOME

# 重新设置环境
source $HOME/.export-esp.sh

# 检查 Rust 目标
rustup target list | grep esp
```

### 问题 2：CMake 找不到 Rust 库

**检查**：
1. Rust 库是否已构建：`ls rust_tasks/target/xtensa-esp32s3-espidf/release/librust_tasks.a`
2. CMakeLists.txt 中的路径是否正确
3. 目标架构是否匹配（xtensa-esp32s3-espidf vs xtensa-esp32-espidf）

**解决**：
```bash
# 手动构建 Rust 库
cd rust_tasks
cargo build --release --target xtensa-esp32s3-espidf

# 检查库文件
ls -lh target/xtensa-esp32s3-espidf/release/librust_tasks.a
```

### 问题 3：链接错误

**错误**：`undefined reference to rust_test`

**解决**：
1. 确保函数使用 `#[no_mangle]` 和 `extern "C"`
2. 确保 CMakeLists.txt 正确链接库
3. 清理并重新构建：
```bash
idf.py fullclean
cd rust_tasks && cargo clean
cd .. && idf.py build
```

### 问题 4：目标架构不匹配

**检查你的芯片**：
```bash
# 查看 sdkconfig
grep CONFIG_IDF_TARGET sdkconfig

# 根据芯片选择正确的 Rust 目标：
# ESP32: xtensa-esp32-espidf
# ESP32-S2: xtensa-esp32s2-espidf
# ESP32-S3: xtensa-esp32s3-espidf
# ESP32-C3: riscv32imc-esp-espidf
# ESP32-C6: riscv32imac-esp-espidf
```

## 快速验证命令

### 一键构建和测试

```bash
#!/bin/bash
# 设置环境
source $HOME/.export-esp.sh

# 构建 Rust
cd rust_tasks
cargo build --release --target xtensa-esp32s3-espidf
cd ..

# 构建 ESP-IDF
idf.py build

# 烧录和监控
idf.py flash monitor
```

保存为 `build_rust.sh`，然后：
```bash
chmod +x build_rust.sh
./build_rust.sh
```

## 验证清单

- [ ] Rust 工具链安装成功（`rustc --version`）
- [ ] ESP-IDF Rust 工具链安装成功（`echo $ESP_IDF_VERSION`）
- [ ] rust_tasks 文件夹创建在项目根目录
- [ ] Cargo.toml 配置正确
- [ ] lib.rs 包含测试函数
- [ ] CMakeLists.txt 已修改
- [ ] Rust 库可以构建（`cargo build --release`）
- [ ] ESP-IDF 项目可以链接（`idf.py build`）
- [ ] 可以看到 Rust 日志输出

## 下一步

验证成功后：
1. ✅ 开始迁移业务逻辑到 Rust
2. ✅ 实现混合架构（C 控制硬件，Rust 处理逻辑）
3. ✅ 逐步增加 Rust 代码比例

