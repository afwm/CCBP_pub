# -*- coding: utf-8 -*-

BUTTON_STYLE = """
QPushButton {
    /* Slightly lighter gradient for standard state */
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5F5F5F, stop:1 #4F4F4F);
    color: #E0E0E0; /* Keep text bright */
    border: 1px solid #6A6A6A; /* Slightly lighter border */
    border-radius: 4px; 
    padding: 3px 8px; /* Reduced vertical padding (3px), increased horizontal (8px) */
    min-height: 20px; /* Adjust min-height based on new padding */
}
QPushButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6F6F6F, stop:1 #5F5F5F); 
    border: 1px solid #808080;
}
QPushButton:pressed {
    background-color: #4A4A4A; /* Slightly darker pressed state */
    border: 1px solid #555555;
}
QPushButton:disabled {
    /* Keep the original distinct disabled style */
    background-color: #444444; 
    color: #888888; 
    border: 1px solid #222222;
}
""" 