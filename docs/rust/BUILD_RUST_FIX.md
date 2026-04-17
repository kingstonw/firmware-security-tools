# 修复 Rust 库构建问题

## 问题
```
ninja: error: 'librust_tasks.a', needed by 'WatusiPanel.elf', missing and no known rule to make it
```

## 原因
CMake 的 `add_custom_target` 不会自动生成输出文件，Ninja 不知道如何构建这个文件。

## 解决方案

我已经修复了 `main/CMakeLists.txt`，使用 `add_custom_command` 来指定输出文件。

### 修复内容

**之前（错误）**：
```cmake
add_custom_target(rust_tasks_build
    COMMAND cargo build ...
)
```

**现在（正确）**：
```cmake
add_custom_command(
    OUTPUT ${RUST_LIB}  # 指定输出文件
    COMMAND cargo build ...
)

add_custom_target(rust_tasks_build_target
    DEPENDS ${RUST_LIB}  # 依赖输出文件
)
```

## 构建步骤

### 方法 1：让 CMake 自动构建（推荐）

```bash
# 设置环境
source $HOME/.export-esp.sh

# 清理并重新构建（CMake 会自动构建 Rust 库）
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2
idf.py fullclean
idf.py build
```

### 方法 2：手动先构建 Rust 库

```bash
# 设置环境
source $HOME/.export-esp.sh

# 手动构建 Rust 库
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2/rust_tasks
cargo build --release --target xtensa-esp32s3-espidf

# 验证库文件
ls -lh target/xtensa-esp32s3-espidf/release/librust_tasks.a

# 然后构建 ESP-IDF 项目
cd ..
idf.py build
```

## 验证

构建成功后，你应该看到：
1. CMake 配置阶段：`Building Rust tasks library`
2. 链接阶段：成功链接 `librust_tasks.a`
3. 运行时：看到 `🚀 Rust function called from C!` 日志

## 如果仍然失败

### 检查 1：验证 Rust 环境

```bash
source $HOME/.export-esp.sh
echo $ESP_IDF_VERSION
rustc --version
cargo --version
```

### 检查 2：验证 Rust 目标

```bash
rustup target list | grep esp32s3
# 应该看到: xtensa-esp32s3-espidf
```

### 检查 3：手动构建测试

```bash
cd rust_tasks
cargo build --release --target xtensa-esp32s3-espidf
# 如果失败，查看错误信息
```

### 检查 4：验证 CMakeLists.txt

确保 `main/CMakeLists.txt` 包含：
- `add_custom_command(OUTPUT ${RUST_LIB} ...)`
- `add_custom_target(... DEPENDS ${RUST_LIB})`
- `add_dependencies(${COMPONENT_LIB} rust_tasks_build_target)`
- `target_link_libraries(... ${RUST_LIB})`

## 快速修复命令

```bash
source $HOME/.export-esp.sh && \
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2 && \
idf.py fullclean && \
idf.py build
```

CMake 现在应该能够自动构建 Rust 库了。

