# 修复 CMake 构建 Rust 时的环境问题

## 问题

即使 `rustc` 和 `target` 都正确，构建时仍然出现：
```
error[E0463]: can't find crate for `core`
```

## 根本原因

**CMake 构建时没有使用 `espup` 安装的工具链环境**。

ESP-IDF 的 Rust 目标需要：
1. 通过 `espup install` 安装的特殊工具链
2. 环境变量（通过 `source $HOME/.export-esp.sh` 设置）
3. 标准库（由 `espup` 提供，不是标准的 `rustup`）

当 CMake 运行 `cargo build` 时，如果没有加载 `.export-esp.sh`，就会使用标准的 Rust 工具链，导致找不到 `core` crate。

## 解决方案

### 方案 1：修复 CMakeLists.txt（已更新）

已更新 `main/CMakeLists.txt`，确保构建时加载 ESP-IDF 环境：

```cmake
COMMAND ${CMAKE_COMMAND} -E env 
        "CARGO_TARGET_DIR=${RUST_TARGET_DIR}"
        "PATH=$ENV{PATH}"
        "HOME=$ENV{HOME}"
        bash -c "source $$HOME/.export-esp.sh 2>/dev/null || true && cargo build --release ..."
```

### 方案 2：确保 espup 工具链已安装

**必须先运行**：

```bash
# 1. 设置 ESP-IDF 路径
export ESP_IDF_PATH=/Users/kingstonw/esp/v6.0/esp-idf

# 2. 安装 ESP-IDF Rust 工具链（如果还没有）
espup install

# 3. 验证安装
source $HOME/.export-esp.sh
echo $ESP_IDF_VERSION
rustup target list | grep esp32s3
```

### 方案 3：手动测试构建

在修复 CMake 之前，先手动测试 Rust 构建：

```bash
# 设置环境
source $HOME/.export-esp.sh

# 手动构建
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2/rust_tasks
cargo build --release --target xtensa-esp32s3-espidf
```

如果手动构建成功，但 CMake 构建失败，说明是环境变量问题。

## 验证步骤

### 1. 检查 espup 工具链

```bash
# 检查 .export-esp.sh 是否存在
test -f $HOME/.export-esp.sh && echo "✅ 存在" || echo "❌ 不存在，需要运行: espup install"

# 检查环境变量
source $HOME/.export-esp.sh
echo "ESP_IDF_VERSION: $ESP_IDF_VERSION"
echo "RUSTC: $(which rustc)"
```

### 2. 检查 Rust 目标

```bash
source $HOME/.export-esp.sh
rustup target list | grep esp32s3
# 应该看到: xtensa-esp32s3-espidf (installed)
```

### 3. 手动测试构建

```bash
source $HOME/.export-esp.sh
cd rust_tasks
cargo build --release --target xtensa-esp32s3-espidf
```

### 4. 测试 CMake 构建

```bash
# 确保环境已设置
source $HOME/.export-esp.sh

# 清理并重新构建
cd /Users/kingstonw/FCS_ws/WatusiPanel-V2
idf.py fullclean
idf.py build
```

## 常见问题

### Q: 为什么手动构建成功，但 CMake 构建失败？

**A**: CMake 构建时没有加载 `.export-esp.sh`，导致使用了标准的 Rust 工具链而不是 ESP-IDF 工具链。

**解决**: 已更新 CMakeLists.txt，在构建命令中自动加载环境。

### Q: `espup install` 失败怎么办？

**A**: 
1. 检查 ESP-IDF 路径：`export ESP_IDF_PATH=/path/to/esp-idf`
2. 检查网络连接（需要下载工具链）
3. 检查磁盘空间（工具链约 1-2 GB）

### Q: 可以不用 `espup`，直接用 `rustup` 吗？

**A**: 不可以。ESP-IDF 的 Rust 目标需要特殊的工具链和标准库，只能通过 `espup` 安装。

### Q: 如何确认使用的是正确的工具链？

**A**: 
```bash
source $HOME/.export-esp.sh
rustc --version
# 应该显示 espup 安装的工具链版本，而不是标准的 rustc
```

## 完整修复流程

```bash
# 1. 安装 ESP-IDF Rust 工具链（如果还没有）
export ESP_IDF_PATH=/Users/kingstonw/esp/v6.0/esp-idf
espup install
source $HOME/.export-esp.sh

# 2. 验证安装
echo $ESP_IDF_VERSION
rustup target list | grep esp32s3

# 3. 手动测试构建
cd rust_tasks
cargo build --release --target xtensa-esp32s3-espidf

# 4. 清理并重新构建 ESP-IDF 项目
cd ..
source $HOME/.export-esp.sh  # 确保环境已设置
idf.py fullclean
idf.py build
```

## 检查清单

- [ ] `espup` 已安装（`espup --version`）
- [ ] `espup install` 已运行（`test -f $HOME/.export-esp.sh`）
- [ ] 环境变量已设置（`source $HOME/.export-esp.sh`）
- [ ] Rust 目标已安装（`rustup target list | grep esp32s3`）
- [ ] 手动构建成功（`cargo build --release --target xtensa-esp32s3-espidf`）
- [ ] CMakeLists.txt 已更新（包含环境加载）
- [ ] CMake 构建成功（`idf.py build`）

