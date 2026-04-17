# 修复缺失的标准库问题

## 问题

即使 `source ~/export-esp.sh` 正确，仍然出现：
```
error[E0463]: can't find crate for `core`
```

## 根本原因

**标准库目录不存在**：
```
/Users/kingstonw/.rustup/toolchains/esp/lib/rustlib/xtensa-esp32s3-espidf/
```

这说明 `espup install` 可能没有完全成功，或者标准库没有正确安装。

## 解决方案

### 方法 1：重新运行 espup install（推荐）

```bash
# 1. 设置 ESP-IDF 路径
export ESP_IDF_PATH=/Users/kingstonw/esp/v6.0/esp-idf

# 2. 重新安装（这会确保所有组件都正确安装）
espup install

# 3. 设置环境
source $HOME/export-esp.sh

# 4. 验证标准库
ls -la $HOME/.rustup/toolchains/esp/lib/rustlib/xtensa-esp32s3-espidf/
# 应该看到 libcore-*.rlib 等文件
```

### 方法 2：检查 espup 安装状态

```bash
# 检查工具链目录
ls -la $HOME/.rustup/toolchains/esp/

# 检查已安装的目标
source $HOME/export-esp.sh
rustc --print target-list | grep esp32s3

# 检查标准库
ls -la $HOME/.rustup/toolchains/esp/lib/rustlib/
```

### 方法 3：使用 build-std（临时方案）

如果标准库确实缺失，可以尝试使用 `-Z build-std`：

```toml
# 在 Cargo.toml 中添加
[unstable]
build-std = ["core"]
```

但这不是推荐方案，应该通过 `espup install` 正确安装标准库。

## 验证步骤

```bash
# 1. 设置环境
source $HOME/export-esp.sh

# 2. 检查工具链
rustc --version
# 应该显示 esp 工具链版本

# 3. 检查目标
rustc --print target-list | grep esp32s3
# 应该看到: xtensa-esp32s3-espidf

# 4. 检查标准库
ls $HOME/.rustup/toolchains/esp/lib/rustlib/xtensa-esp32s3-espidf/
# 应该看到 libcore-*.rlib 等文件

# 5. 测试构建
cd rust_tasks
cargo build --release --target xtensa-esp32s3-espidf
```

## 关于 `source ~/export-esp.sh`

**确认：`source ~/export-esp.sh` 是正确的！**

- 文件路径：`$HOME/export-esp.sh`（无前导点）
- 你的 CMakeLists.txt 已正确检查两个路径：
  - `$HOME/export-esp.sh` ✅
  - `$HOME/.export-esp.sh` ✅（作为后备）

## 下一步

1. **重新运行 `espup install`** 确保标准库正确安装
2. **验证标准库目录存在**
3. **重新构建项目**

