"""
Letter-to-pronunciation mapping for the Sloan closed-set recognizer.

Key: canonical uppercase letter.
Value: common Vietnamese spoken forms or close ASR variants.
"""

LETTER_TO_PRONUNCIATIONS = {
    "C": ["c", "xê", "cờ", "xi"],
    "D": ["d", "dê", "đê", "dờ", "đờ"],
    "H": ["h", "hờ", "hắt"],
    "K": ["k", "ca", "kay"],
    "N": ["n", "nờ", "en nờ"],
    "O": ["o", "ô"],
    "R": ["r", "rờ", "e rờ", "ê rờ"],
    "S": ["s", "sờ", "ét"],
    "V": ["v", "vê", "vờ", "vi"],
    "Z": ["z", "dét", "jet"],
    "X": ["không thấy", "không rõ", "không biết", "bỏ qua"],
}
