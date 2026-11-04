"""All UI strings: key -> (Hebrew, English)."""
from i18n import S

S.update({
    # ---- generic
    "open": ("פתיחה", "Open"),
    "save": ("שמירה", "Save"),
    "save_as": ("שמירה בשם…", "Save as…"),
    "print": ("הדפסה", "Print"),
    "undo": ("ביטול פעולה", "Undo"),
    "redo": ("שחזור פעולה", "Redo"),
    "cancel": ("ביטול", "Cancel"),
    "delete": ("מחיקה", "Delete"),
    "done": ("סיום", "Done"),
    "copy": ("העתקה", "Copy"),
    "copied": ("הטקסט הועתק", "Text copied"),
    "page": ("עמוד", "Page"),
    "untitled": ("ללא שם", "Untitled"),
    "more": ("עוד…", "More…"),
    "clear": ("ניקוי", "Clear"),

    # ---- welcome
    "welcome_hint": ("גררו קובץ PDF לכאן, או לחצו על הכפתור", "Drop a PDF here, or click the button"),
    "open_pdf": ("פתיחת קובץ PDF", "Open a PDF file"),
    "recent_files": ("קבצים אחרונים", "Recent files"),

    # ---- toolbar
    "search": ("חיפוש", "Search"),
    "sidebar": ("חלונית צד (עמודים / תוכן / הערות)", "Side panel (pages / contents / notes)"),
    "prev_page": ("עמוד קודם", "Previous page"),
    "next_page": ("עמוד הבא", "Next page"),
    "zoom_in": ("הגדלה", "Zoom in"),
    "zoom_out": ("הקטנה", "Zoom out"),
    "fit_width": ("התאמה לרוחב", "Fit width"),
    "fit_page": ("התאמה לעמוד", "Fit page"),
    "rotate": ("סיבוב העמודים", "Rotate pages"),
    "dark_mode": ("מצב כהה", "Dark mode"),
    "invert_pages": ("היפוך צבעי העמודים (קריאה בלילה)", "Invert page colors (night reading)"),
    "new_window": ("חלון חדש", "New window"),
    "language": ("שפה", "Language"),
    "author_name": ("שם מחבר להערות…", "Author name for comments…"),
    "author_prompt": ("השם שיופיע על הערות וסימונים:", "Name shown on comments and markups:"),
    "help": ("עזרה", "Help"),
    "about": ("אודות", "About"),

    "tool_select": ("בחירה", "Select"),
    "tool_highlight": ("מרקר", "Highlight"),
    "tool_underline": ("קו תחתי", "Underline"),
    "tool_strike": ("קו חוצה", "Strikeout"),
    "tool_note": ("פתק", "Note"),
    "tool_text": ("טקסט", "Text"),
    "tool_sign": ("חתימה", "Sign"),
    "underline": ("קו תחתי", "Underline"),
    "strike": ("קו חוצה", "Strikeout"),

    "hl_yellow": ("צהוב", "Yellow"),
    "hl_green": ("ירוק", "Green"),
    "hl_pink": ("ורוד", "Pink"),
    "hl_blue": ("כחול", "Blue"),
    "hl_orange": ("כתום", "Orange"),

    "text_free": ("טקסט חופשי…", "Free text…"),
    "text_check": ("סימון V", "Check mark"),
    "text_cross": ("סימון X", "Cross mark"),
    "text_date": ("תאריך של היום", "Today's date"),
    "text_size": ("גודל טקסט", "Text size"),
    "text_color": ("צבע טקסט", "Text color"),
    "ink_black": ("שחור", "Black"),
    "ink_blue": ("כחול", "Blue"),
    "ink_red": ("אדום", "Red"),

    # ---- hints (status bar)
    "hint_select": ("גררו על טקסט לסימון · קליק על פתק/חתימה לעריכה · Delete למחיקה",
                    "Drag over text to select · click a note/signature to edit · Delete removes"),
    "hint_highlight": ("גררו על הטקסט כדי לסמן אותו (גרירה על אזור ללא טקסט מסמנת מלבן)",
                       "Drag over text to mark it (dragging on non-text marks a rectangle)"),
    "hint_note": ("לחצו במקום שבו תרצו להניח פתק", "Click where you want the note"),
    "hint_text": ("לחצו במקום שבו תרצו להקליד · Enter לאישור · Esc לביטול",
                  "Click where you want to type · Enter confirms · Esc cancels"),
    "hint_preset": ("לחצו במקום שבו תרצו להניח את הסימון", "Click where you want to place it"),
    "hint_sign": ("לחצו במקום שבו תרצו לחתום · אחר כך אפשר לגרור ולשנות גודל",
                  "Click where you want to sign · then drag / resize it"),

    # ---- popups / context menu
    "note_placeholder": ("כתבו כאן… (עברית ואנגלית נתמכות)", "Type here… (Hebrew and English supported)"),
    "text_hint": ("Enter = אישור · Shift+Enter = שורה חדשה · Esc = ביטול",
                  "Enter = OK · Shift+Enter = new line · Esc = cancel"),
    "comment": ("הערה", "Comment"),
    "delete_markup": ("מחיקת הסימון", "Delete markup"),
    "highlight_comment": ("מרקר + הערה…", "Highlight + comment…"),
    "edit_note": ("עריכת הפתק", "Edit note"),
    "edit_text": ("עריכת הטקסט", "Edit text"),
    "add_note_here": ("הוספת פתק כאן", "Add note here"),
    "add_text_here": ("הקלדת טקסט כאן", "Type text here"),

    # ---- signature
    "new_signature": ("חתימה חדשה…", "New signature…"),
    "delete_signature": ("מחיקת חתימה שמורה", "Delete a saved signature"),
    "delete_signature_q": ("למחוק את החתימה השמורה?", "Delete this saved signature?"),
    "tab_draw": ("לצייר", "Draw"),
    "tab_type": ("להקליד", "Type"),
    "draw_here": ("חתמו כאן בעכבר / עט / אצבע", "Sign here with mouse / pen / finger"),
    "type_name": ("הקלידו את השם", "Type your name"),
    "thickness": ("עובי:", "Thickness:"),
    "ink": ("צבע דיו:", "Ink:"),
    "save_signature": ("שמירה והוספה למסמך", "Save and use"),

    # ---- sidebar / search
    "tab_pages": ("עמודים", "Pages"),
    "tab_contents": ("תוכן", "Contents"),
    "tab_notes": ("הערות", "Notes"),
    "no_notes": ("אין עדיין הערות במסמך", "No notes in this document yet"),
    "search_placeholder": ("חיפוש במסמך…", "Search in document…"),
    "find_next": ("התוצאה הבאה", "Next result"),
    "find_prev": ("התוצאה הקודמת", "Previous result"),
    "no_results": ("אין תוצאות", "No results"),

    # ---- files / save
    "file_missing": ("הקובץ לא נמצא:\n{0}", "File not found:\n{0}"),
    "open_failed": ("לא ניתן לפתוח את הקובץ:\n{0}", "Could not open the file:\n{0}"),
    "empty_pdf": ("בקובץ אין עמודים.", "The file has no pages."),
    "password": ("סיסמה", "Password"),
    "password_prompt": ("הקובץ מוגן בסיסמה. הקלידו סיסמה:", "This file is password protected. Enter the password:"),
    "wrong_password": ("הסיסמה שגויה.", "Wrong password."),
    "unsaved_q": ("יש שינויים שלא נשמרו ב-\"{0}\". מה לעשות?", "\"{0}\" has unsaved changes. What now?"),
    "discard": ("לא לשמור", "Discard"),
    "overwrite_q": ("לשמור את השינויים בתוך הקובץ המקורי \"{0}\"?\n(אפשר גם לשמור עותק חדש ולהשאיר את המקור כמו שהוא.)",
                    "Save the changes into the original file \"{0}\"?\n(Or save a new copy and leave the original untouched.)"),
    "overwrite": ("שמירה על המקור", "Overwrite original"),
    "save_copy": ("שמירת עותק חדש…", "Save a new copy…"),
    "copy_suffix": ("_ערוך", "_edited"),
    "nothing_to_save": ("אין שינויים לשמירה", "Nothing to save"),
    "saved_to": ("נשמר: {0}", "Saved: {0}"),
    "save_failed": ("השמירה נכשלה:\n{0}\n\nייתכן שהקובץ פתוח בתוכנה אחרת.",
                    "Saving failed:\n{0}\n\nThe file may be open in another program."),

    # ---- printing
    "printing": ("מדפיס…", "Printing…"),
    "print_failed": ("לא ניתן להתחיל הדפסה במדפסת שנבחרה.", "Could not start printing on the selected printer."),

    # ---- help / about
    "help_text": (
        "• סימון טקסט: גררו עם העכבר על טקסט. אחר כך לחצו על \"מרקר\" או קליק ימני.\n"
        "• מרקר: בחרו \"מרקר\" וגררו על הטקסט (חץ ליד הכפתור = צבעים).\n"
        "• פתק: בחרו \"פתק\", לחצו על הדף וכתבו. עברית ואנגלית, כל פסקה בכיוון שלה.\n"
        "• טקסט על הדף: למילוי טפסים (שם, תאריך, V). אפשר ללחוץ פעמיים על טקסט כדי לערוך.\n"
        "• חתימה: בחרו \"חתימה\" > \"חתימה חדשה\" (ציור או הקלדה). החתימה נשמרת ואפשר להניח אותה בלחיצה, "
        "לגרור ולשנות גודל.\n"
        "• Delete מוחק את הפריט שנבחר · Ctrl+Z מבטל · Ctrl+F חיפוש · Ctrl+P הדפסה · Ctrl+S שמירה.\n"
        "• מקשים: V בחירה · H מרקר · N פתק · T טקסט · S חתימה.\n"
        "• כל ההערות, הסימונים והחתימות נשמרים בתוך קובץ ה-PDF עצמו.",
        "• Select text: drag over it, then click Highlight or right-click.\n"
        "• Highlight: choose Highlight and drag over text (arrow next to it = colors).\n"
        "• Note: choose Note, click on the page and type. Hebrew and English, each paragraph in its own direction.\n"
        "• Text on page: for filling forms (name, date, check mark). Double-click text to edit it.\n"
        "• Sign: choose Sign > New signature (draw or type). It is saved; click to place it, then drag / resize.\n"
        "• Delete removes the selected item · Ctrl+Z undo · Ctrl+F search · Ctrl+P print · Ctrl+S save.\n"
        "• Keys: V select · H highlight · N note · T text · S sign.\n"
        "• All comments, markups and signatures are stored inside the PDF file itself."),
    "about_text": ("{0} — קורא PDF קל ומהיר עם הערות בעברית, סימון, חתימה והדפסה.",
                   "{0} — a light and fast PDF reader with Hebrew notes, highlighting, signing and printing."),
})
