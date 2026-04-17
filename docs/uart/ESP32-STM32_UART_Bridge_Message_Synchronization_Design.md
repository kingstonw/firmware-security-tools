# UART Protocol Documentation

## Table of Contents
- [Return Value 3 - SSID Configuration Frame](#return-value-3-ssid-frame)
- [Return Value 4 - PASSWORD Configuration Frame](#return-value-4-password-frame)
- [Return Value 5 - UART Bridge Mode Frame](#return-value-5-uart-bridge-frame)

---

## Return Value 3 (SSID Frame)

### Overview
 **SSID Configuration Frame** 

### Frame Structure
```
Byte Position:  [0]    [1]    [2]    [3]    [4]      [5]       [6]       [7+]        [n-1]
                0xCC   0xCA   0xFF   0xFF   FCODE    LEN_HIGH  LEN_LOW   DATA[...]   CHECKSUM
                 
Header (4 bytes) | Function Code | Data Length (2 bytes) | Variable Data | Checksum
```

### Frame Header
- **Byte 0-1:** `0xCC 0xCA` - SSID frame identifier
- **Byte 2-3:** `0xFF 0xFF` - Reserved/Fixed bytes

### Function Codes (FCODE at Byte 4)
- **0x01** = READ SSID - Request to read current SSID configuration
  - *Note: When top drawer sends READ request, response is transmitted to bottom drawer*
  - *Note: When top drawer sends READ request (FCODE 0x01), response frame (FCODE 0x01) is transmitted to bottom drawer*
- **0x06** = WRITE SSID - Send new SSID data to device

### Data Length (Bytes 5-6)
- **Byte 5:** High byte of data length
- **Byte 6:** Low byte of data length
- Combined as: `totalLength = (LEN_HIGH << 8) | LEN_LOW`
- **Maximum payload length:** 32 bytes

### Variable Data Payload (Bytes 7 to n-1)
- SSID/PASSWORD string or configuration data
- Length determined by `LEN_HIGH` and `LEN_LOW`
- **Range:** 1-32 bytes (frames exceeding 32 bytes are rejected)

### Checksum (Last Byte)
- XOR checksum of all data bytes (excluding checksum itself)
- Used to validate frame integrity


---

## Return Value 4 (PASSWORD Frame)

### Overview
 **PASSWORD Configuration Frame** has been received and processed. This frame type is used for reading or writing WiFi password settings.

### Frame Structure
```
Byte Position:  [0]    [1]    [2]    [3]    [4]      [5]       [6]       [7+]        [n-1]
                 0xBB   0xBA   0xFF   0xFF   FCODE    LEN_HIGH  LEN_LOW   DATA[...]   CHECKSUM
                 
Header (4 bytes) | Function Code | Data Length (2 bytes) | Variable Data | Checksum
```

### Frame Header
- **Byte 0-1:** `0xBB 0xBA` - PASSWORD frame identifier
- **Byte 2-3:** `0xFF 0xFF` - Reserved/Fixed bytes

### Function Codes (FCODE at Byte 4)
- **0x01** = READ PASSWORD - Request to read current password configuration
  - *Note: When top drawer sends READ request, response is transmitted to bottom drawer*
- **0x06** = WRITE PASSWORD - Send new password data to device

### Data Length (Bytes 5-6)
- **Byte 5:** High byte of data length
- **Byte 6:** Low byte of data length
- Combined as: `totalLength = (LEN_HIGH << 8) | LEN_LOW`
- **Maximum payload length:** 32 bytes

### Variable Data Payload (Bytes 7 to n-1)
- Password string or configuration data
- Length determined by `LEN_HIGH` and `LEN_LOW`
- **Range:** 1-32 bytes (frames exceeding 32 bytes are rejected)

### Checksum (Last Byte)
- XOR checksum of all data bytes (excluding checksum itself)
- Used to validate frame integrity


---

## Return Value 5 (UART Bridge Frame)

### Overview
**UART Bridge Mode Frame** enables transparent bidirectional data transfer between UART1 (Top Drawer/ESP32-1) and UART6 (Bottom Drawer/ESP32-2). The MCU acts as a bridge, forwarding packets in both directions without processing the payload data. This mode is useful for direct communication between the two ESP32 modules through the main controller.

### Frame Structure
```
Byte Position:  [0]    [1]    [2]    [3]    [4]      [5]       [6]       [7+]        [n-1]
                0xDD   0xDA   0xFF   0xFF   0xFF     LEN_HIGH  LEN_LOW   DATA[...]   CHECKSUM
                 
Header (7 bytes) | Data Length (2 bytes) | Variable Payload Data | Checksum
```

### Frame Header
- **Byte 0-1:** `0xDD 0xDA` - UART Bridge frame identifier
- **Byte 2-4:** `0xFF 0xFF 0xFF` - Reserved/Fixed bytes

### Operation Mode
- **TRANSPARENT FORWARDING** - Bridge mode does not use function codes (READ/WRITE)
- Packets received on UART1 with `0xDD 0xDA` header are forwarded to UART6
- Packets received on UART6 with `0xDD 0xDA` header are forwarded to UART1
- The entire packet (including header and checksum) is transmitted as-is

### Data Length (Bytes 5-6)
- **Byte 5:** High byte of data length
- **Byte 6:** Low byte of data length
- Combined as: `totalLength = (LEN_HIGH << 8) | LEN_LOW`
- **Maximum payload length:** 120 bytes (RX_DATA_MAX - 8)

### Variable Data Payload (Bytes 7 to n-1)
- Transparent payload data to be forwarded
- Can contain any application-specific data or protocol
- Length determined by `LEN_HIGH` and `LEN_LOW`
- **Range:** 1-120 bytes (frames exceeding limit are rejected)
- Content is not interpreted by the MCU

### Checksum (Last Byte)
- XOR checksum of all data bytes (excluding checksum itself)
- Calculated at sender, validated at receiver
- Used to validate frame integrity during transmission

### Bridge Flow Examples

#### Example 1: UART1 → UART6
```
Top Drawer (UART1) sends:
  [0xDD][0xDA][0xFF][0xFF][0xFF][0x00][0x05][H][E][L][L][O][CHKSUM]
  
MCU forwards to Bottom Drawer (UART6):
  [0xDD][0xDA][0xFF][0xFF][0xFF][0x00][0x05][H][E][L][L][O][CHKSUM]
```

#### Example 2: UART6 → UART1
```
Bottom Drawer (UART6) sends:
  [0xDD][0xDA][0xFF][0xFF][0xFF][0x00][0x03][A][C][K][CHKSUM]
  
MCU forwards to Top Drawer (UART1):
  [0xDD][0xDA][0xFF][0xFF][0xFF][0x00][0x03][A][C][K][CHKSUM]
```



