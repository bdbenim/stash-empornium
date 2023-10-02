from PIL import Image

def createContactSheet(files: list[str], target_width: int, row_height: int, output: str) -> str | None:
    #working_imgs: list[Image.Image] = []
    row_files: list[str] = []
    rows: list[Image.Image] = []
    row_width = 0
    total_height = 0

    for file in files:
        img = None
        try:
            with Image.open(file) as img:
                w = img.width
                if img.height > row_height:
                    w = int((row_height/img.height)*img.width)
                if (row_width+w)>target_width:
                    delta = target_width / row_width
                    h = int(row_height * delta)
                    row = Image.new('RGB', (target_width, h))
                    left = 0
                    for wfile in row_files:
                        with Image.open(wfile) as wimg:
                            wimg.thumbnail((wimg.width, h), Image.LANCZOS)
                            row.paste(wimg, (left, 0))
                            left += wimg.width

                    rows.append(row)
                    total_height += row.height

                    row_files.clear()
                    row_files.append(file)
                    row_width = w
                else:
                    row_files.append(file)
                    row_width += w
        except:
            return None
            
    sheet = Image.new('RGB', (target_width, total_height))
    top = 0
    for row in rows:
        bbox = (0, top)
        sheet.paste(row, bbox)
        top += row.height
        row.close()
    sheet.save(output)
    sheet.show()
    sheet.close()
    return output