"""Generate a small sample PDF (English + Hebrew + a signature line) for manual / automated tests."""
import sys
import pymupdf

out = sys.argv[1] if len(sys.argv) > 1 else "sample.pdf"
doc = pymupdf.open()
arch = pymupdf.Archive("C:/Windows/Fonts")
css = "@font-face{font-family:ar;src:url(arial.ttf);} body{font-family:ar;font-size:13pt;}"
for n in range(1, 4):
    page = doc.new_page(width=595, height=842)
    page.insert_htmlbox(pymupdf.Rect(50, 40, 545, 110), f"<h2>Sample contract - page {n}</h2>", css=css, archive=arch)
    page.insert_htmlbox(
        pymupdf.Rect(50, 110, 545, 330),
        "<p>This agreement is made between the parties on the date written below. "
        "The service provider shall deliver the work described in Appendix A within thirty days.</p>"
        "<p>Payment terms: net 30 from the date of invoice. Late payments accrue interest.</p>",
        css=css, archive=arch)
    page.insert_htmlbox(
        pymupdf.Rect(50, 340, 545, 560),
        '<div dir="rtl"><p>הסכם זה נערך בין הצדדים ביום הנקוב להלן. ספק השירות מתחייב לספק את העבודה '
        'המפורטת בנספח א׳ בתוך שלושים יום.</p><p>תנאי תשלום: שוטף + 30 מתאריך החשבונית. '
        'איחור בתשלום יישא ריבית.</p></div>',
        css=css, archive=arch)
    page.draw_line((60, 700), (260, 700))
    page.insert_text((60, 715), "Signature / חתימה", fontsize=10)
    page.draw_line((340, 700), (540, 700))
    page.insert_text((340, 715), "Date / תאריך", fontsize=10)
doc.set_toc([[1, "Intro", 1], [1, "Hebrew section", 2], [2, "Sub item", 3]])
doc.save(out)
print("saved", out)
