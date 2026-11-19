
LETTER_TO_PRONUNCIATIONS = {
    # Nhóm true
    "DUNG": ["đúng", "đúng rồi"],
    "CHINH_XAC": ["chính xác"],
    "PHAI": ["phải"],
    
    # Nhóm skip
    "BO_QUA": ["bỏ qua"],
    
    #  Nhóm false
    "SAI": ["sai", "sai rồi"],
    "KHONG_PHAI": ["không phải", "hông phải"],
    "KHONG_DUNG": ["không đúng", "hông đúng"],
    "KHONG": ["không", "hông"],
}

# Classifier learns the eight fine-grained phrases above. Public inference
# aggregates their probabilities into these three application-level results.
LABEL_TO_GROUP = {
    "DUNG": "TRUE",
    "CHINH_XAC": "TRUE",
    "PHAI": "TRUE",
    "BO_QUA": "SKIP",
    "SAI": "FALSE",
    "KHONG_PHAI": "FALSE",
    "KHONG_DUNG": "FALSE",
    "KHONG": "FALSE",
}

LABELS = list(LETTER_TO_PRONUNCIATIONS)
GROUPS = ["TRUE", "SKIP", "FALSE"]
