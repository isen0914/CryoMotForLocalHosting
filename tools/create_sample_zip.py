from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import zipfile

out_dir = Path('tools/sample_images')
out_dir.mkdir(parents=True, exist_ok=True)
img_path = out_dir / 'test1.jpg'
# create a simple image with a rectangle (toy object)
img = Image.new('RGB', (640, 480), color=(200, 200, 200))
d = ImageDraw.Draw(img)
d.rectangle([200, 100, 440, 340], outline=(255,0,0), width=6)
d.text((210,110), 'object', fill=(255,0,0))
img.save(img_path)
# zip it
zip_path = Path('tools/sample.zip')
with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as z:
    z.write(img_path, arcname=img_path.name)
print('Created', zip_path.resolve())
