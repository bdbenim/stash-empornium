from PIL import Image

def createContactSheet(files: list[str], target_width: int, row_height: int, output: str) -> str | None:
    working_imgs: list[Image.Image] = []
    rows: list[Image.Image] = []
    row_width = 0
    total_height = 0

    for file in files:
        try:
            img = Image.open(file)
            w = img.width
            if img.height > row_height:
                w = int((row_height/img.height)*img.width)
            if (row_width+w)>target_width:
                delta = target_width / row_width
                h = int(row_height * delta)
                row = Image.new('RGB', (target_width, h))
                left = 0
                for wimg in working_imgs:
                    wimg.thumbnail((wimg.width, h), Image.LANCZOS)
                    row.paste(wimg, (left, 0))
                    left += wimg.width
                    wimg.close()

                rows.append(row)
                total_height += row.height

                working_imgs.clear()
                working_imgs.append(img)
                row_width = w
            else:
                working_imgs.append(img)
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