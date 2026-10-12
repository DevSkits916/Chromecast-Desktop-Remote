"""Bluetooth HID report encoding; independent of Windows and Qt."""

KEYBOARD = {'up': 0x52, 'down': 0x51, 'left': 0x50, 'right': 0x4F,
            'ok': 0x28, 'back': 0x29}
CONSUMER = {'home': 0x223, 'power': 0x30, 'volume_up': 0xE9,
            'volume_down': 0xEA, 'mute': 0xE2, 'play_pause': 0xCD,
            'previous': 0xB6, 'next': 0xB5, 'stop': 0xB7,
            'rewind': 0xB4, 'fast_forward': 0xB3}

# Keyboard report ID 1: modifiers, reserved byte, six keys.
# Consumer report ID 2: one 16-bit usage. IDs live in Report Reference descriptors,
# not in the notification payloads of individual GATT Report characteristics.
REPORT_MAP = bytes.fromhex(
    '05 01 09 06 A1 01 85 01 05 07 19 E0 29 E7 15 00 25 01 '
    '75 01 95 08 81 02 95 01 75 08 81 01 '
    '95 06 75 08 15 00 25 65 05 07 19 00 29 65 81 00 C0 '
    '05 0C 09 01 A1 01 85 02 15 00 26 FF 03 19 00 2A FF 03 '
    '75 10 95 01 81 00 C0')


def reports(pressed):
    unknown = set(pressed) - KEYBOARD.keys() - CONSUMER.keys()
    if unknown:
        raise ValueError(f'Unsupported remote action: {sorted(unknown)[0]}')
    keys = sorted({KEYBOARD[key] for key in pressed if key in KEYBOARD})
    if len(keys) > 6:
        keys = [1] * 6  # HID ErrorRollOver
    keyboard = bytes([0, 0, *keys, *([0] * (6 - len(keys)))])
    # Choose deterministically if several consumer buttons are held.
    consumers = sorted(CONSUMER[key] for key in pressed if key in CONSUMER)
    consumer = (consumers[-1] if consumers else 0).to_bytes(2, 'little')
    return keyboard, consumer
