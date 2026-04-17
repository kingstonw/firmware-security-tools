# Rust 集成快速开始（5 分钟）

## 一键安装（推荐）

```bash
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2
./setup_rust.sh
```

脚本会自动：
- ✅ 检查并安装 Rust
- ✅ 安装 ESP-IDF Rust 工具链
- ✅ 创建 `rust_tasks/` 文件夹
- ✅ 配置所有必要文件
- ✅ 更新 CMakeLists.txt

## 手动安装步骤

### 步骤 1：安装 Rust 工具链（2 分钟）

```bash
# 1. 安装 Rust（如果还没有）
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# 2. 安装 ESP-IDF Rust 工具链
cargo install espup
espup install

# 3. 设置环境变量（添加到 ~/.zshrc）
echo 'source $HOME/.export-esp.sh' >> ~/.zshrc
source $HOME/.export-esp.sh

# 4. 验证
rustc --version
echo $ESP_IDF_VERSION
```

### 步骤 2：创建 rust_tasks 项目（1 分钟）

**位置**：在项目根目录（与 `main/` 同级）

```bash
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2
cargo new --lib rust_tasks
```

**目录结构**：
```
WatusiPanel-V2/
├── main/              ← 原有目录
├── rust_tasks/        ← 新建的 Rust 项目（与 main/ 同级）
│   ├── Cargo.toml
│   ├── src/
│   │   └── lib.rs
│   └── target/        ← 构建输出（自动生成）
└── ...
```

### 步骤 3：配置 Rust 项目（1 分钟）

#### 3.1 编辑 `rust_tasks/Cargo.toml`

```toml
[package]
name = "rust_tasks"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["staticlib"]

[dependencies]
esp-idf-sys = { version = "0.36", features = ["binstart"] }
log = "0.4"

[profile.release]
opt-level = "z"
lto = true
codegen-units = 1
```

#### 3.2 编辑 `rust_tasks/src/lib.rs`

```rust
#![no_std]

use esp_idf_sys::*;
use log::*;

#[no_mangle]
pub extern "C" fn rust_test() {
    info!("🚀 Rust function called from C!");
}

#[no_mangle]
pub extern "C" fn rust_process_button_state(
    pressed: bool,
    duration_ms: u32,
) -> u32 {
    if pressed && duration_ms > 10000 {
        info!("Long press detected from Rust! Duration: {} ms", duration_ms);
        return 1;
    }
    0
}
```

### 步骤 4：配置 ESP-IDF 构建系统（1 分钟）

在 `main/CMakeLists.txt` 的**末尾**添加：

```cmake
# ============================================
# Rust Tasks Integration
# ============================================

set(RUST_TASKS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../rust_tasks")
set(RUST_TARGET_DIR "${RUST_TASKS_DIR}/target")
set(RUST_TARGET "xtensa-esp32s3-espidf")  # 根据你的芯片调整
set(RUST_LIB "${RUST_TARGET_DIR}/${RUST_TARGET}/release/librust_tasks.a")

add_custom_target(rust_tasks_build
    COMMAND ${CMAKE_COMMAND} -E env "CARGO_TARGET_DIR=${RUST_TARGET_DIR}" 
            cargo build --release 
            --manifest-path ${RUST_TASKS_DIR}/Cargo.toml
            --target ${RUST_TARGET}
    WORKING_DIRECTORY ${RUST_TASKS_DIR}
    COMMENT "Building Rust tasks library"
    VERBATIM
)

add_dependencies(${COMPONENT_LIB} rust_tasks_build)

target_link_libraries(${COMPONENT_LIB} PRIVATE ${RUST_LIB})
```

**注意**：根据你的芯片类型调整 `RUST_TARGET`：
- ESP32: `xtensa-esp32-espidf`
- ESP32-S2: `xtensa-esp32s2-espidf`
- ESP32-S3: `xtensa-esp32s3-espidf` ← 你的项目
- ESP32-C3: `riscv32imc-esp-espidf`
- ESP32-C6: `riscv32imac-esp-espidf`

### 步骤 5：添加 Rust 目标（30 秒）

```bash
source $HOME/.export-esp.sh
rustup target add xtensa-esp32s3-espidf
```

### 步骤 6：在 C++ 中测试（30 秒）

在 `main/main.cpp` 的 `app_main()` 函数中添加：

```cpp
// 在文件顶部添加
extern "C" {
    void rust_test();
}

// 在 app_main() 中添加
void app_main() {
    // ... 其他初始化 ...
    
    // 测试 Rust
    ESP_LOGI("MAIN", "Testing Rust...");
    rust_test();
    
    // ... 其他代码 ...
}
```

### 步骤 7：构建和测试（1 分钟）

```bash
# 设置环境
source $HOME/.export-esp.sh

# 首次构建 Rust（可能需要 10-20 分钟）
cd rust_tasks
cargo build --release --target xtensa-esp32s3-espidf
cd ..

# 构建 ESP-IDF 项目
idf.py build

# 烧录和监控
idf.py flash monitor
```

## 验证输出

如果成功，你应该看到：
```
I (xxx) rust_tasks: 🚀 Rust function called from C!
```

## 文件位置总结

```
WatusiPanel-V2/
├── main/
│   ├── CMakeLists.txt          ← 已修改（添加 Rust 构建）
│   ├── main.cpp                 ← 已修改（添加 rust_test() 调用）
│   └── ...
├── rust_tasks/                  ← 新建（与 main/ 同级）
│   ├── Cargo.toml               ← Rust 项目配置
│   ├── src/
│   │   └── lib.rs              ← Rust 代码
│   └── target/                  ← 构建输出
│       └── xtensa-esp32s3-espidf/
│           └── release/
│               └── librust_tasks.a  ← 生成的静态库
└── ...
```

## 常见问题

### Q: rust_tasks 文件夹应该放在哪里？
**A**: 在项目根目录，与 `main/` 文件夹同级。

### Q: 如何知道我的芯片类型？
**A**: 查看 `sdkconfig` 文件中的 `CONFIG_IDF_TARGET`，或运行：
```bash
grep CONFIG_IDF_TARGET sdkconfig
```

### Q: 构建失败怎么办？
**A**: 
1. 确保环境变量已设置：`source $HOME/.export-esp.sh`
2. 确保 Rust 目标已添加：`rustup target list | grep esp`
3. 清理并重新构建：
```bash
cd rust_tasks && cargo clean
cd .. && idf.py fullclean
idf.py build
```

## 下一步

验证成功后，参考 `RUST_TASK_QUICK_START.md` 和 `HYBRID_ARCHITECTURE_ANALYSIS.md` 开始迁移业务逻辑。

