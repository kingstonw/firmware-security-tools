# 修复 Rust 链接错误

## 问题
链接错误：`undefined reference to rust_test`

## 原因
1. CMakeLists.txt 中没有 Rust 构建配置
2. Rust 库还没有构建

## 解决方案

### 步骤 1：确保 CMakeLists.txt 已更新

我已经更新了 `main/CMakeLists.txt`，添加了 Rust 构建配置。

### 步骤 2：构建 Rust 库

```bash
# 设置环境
source $HOME/.export-esp.sh

# 进入 rust_tasks 目录
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2/rust_tasks

# 构建 Rust 库（首次构建可能需要 10-20 分钟）
cargo build --release --target xtensa-esp32s3-espidf

# 验证库文件已生成
ls -lh target/xtensa-esp32s3-espidf/release/librust_tasks.a
```

### 步骤 3：构建 ESP-IDF 项目

```bash
# 返回项目根目录
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2

# 清理之前的构建
idf.py fullclean

# 重新构建（会自动构建 Rust 库）
idf.py build
```

## 如果仍然失败

### 检查 1：验证 Rust 库路径

```bash
# 检查库文件是否存在
ls -lh rust_tasks/target/xtensa-esp32s3-espidf/release/librust_tasks.a

# 如果不存在，手动构建
cd rust_tasks
cargo build --release --target xtensa-esp32s3-espidf
cd ..
```

### 检查 2：验证 CMakeLists.txt

确保 `main/CMakeLists.txt` 末尾包含：

```cmake
# Rust Tasks Integration
set(RUST_TASKS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../rust_tasks")
set(RUST_TARGET_DIR "${RUST_TASKS_DIR}/target")
set(RUST_TARGET "xtensa-esp32s3-espidf")
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

### 检查 3：验证函数声明

确保 `main/main.cpp` 中有：

```cpp
extern "C" {
    void rust_test();
}
```

确保 `rust_tasks/src/lib.rs` 中有：

```rust
#[no_mangle]
pub extern "C" fn rust_test() {
    info!("🚀 Rust function called from C!");
}
```

## 快速修复命令

```bash
# 一键修复
source $HOME/.export-esp.sh && \
cd rust_tasks && \
cargo build --release --target xtensa-esp32s3-espidf && \
cd .. && \
idf.py fullclean && \
idf.py build
```

