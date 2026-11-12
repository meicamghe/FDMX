# راهنمای GNS Downloader نسخه 6.40.2

GNS Downloader یک دانلودمنیجر دسکتاپ مبتنی بر Python و PySide6 است.

## نسخه و محیط اجرا

- **نسخه برنامه:** 6.40.2
- **فایل اصلی و مرجع پروژه:** `FDMX_v6_36.py`
- **نسخه Python:** **3.12**
- **ویندوز:** بسته‌های اجرایی Windows 10/11 نسخه ۶۴ بیتی
- **لینوکس:** اجرای سورس فعلی با دستور `python ubuntu.py` یا `python FDMX_v6_36.py`
- **ظاهر برنامه:** در ویندوز تم Windows 11 Fluent و در لینوکس تم Ubuntu Yaru به‌صورت خودکار انتخاب می‌شود.
- تب Theme Studio و Plugin Manager در رابط برنامه وجود ندارند.

## تغییرات نسخه 6.40.2

- شماره نسخه در سورس برنامه، نصب‌کننده ویندوز و بسته انتشار هماهنگ شد. این اصلاح مشکل پیشنهاد دانلود تکراری همان نسخه پس از نصب را برطرف می‌کند.
- انتشار رسمی [نسخه 6.40.2](https://github.com/meicamghe/FDMX/releases/tag/v6.40.2) در تاریخ 2026-11-11 انجام شده و فایل‌های نصب ویندوز در ادامه لینک شده‌اند.

## قابلیت‌های معرفی‌شده در نسخه 6.40

- بخش **About** اکنون سازنده را با نام **MeysamGNS** معرفی می‌کند و ذکر می‌کند که توسعه با کمک **ChatGPT** انجام شده است.
- از منوی **Help → Check for updates** می‌توان نسخه پایدار جدید را در GitHub بررسی کرد. در ویندوز، فایل Setup نسخه جدید دریافت می‌شود و پس از بررسی اندازه و در صورت وجود، SHA-256، امکان اجرای نصب‌کننده نمایش داده می‌شود.
- تم Ubuntu Yaru برای اجرای لینوکس اضافه شده است؛ ظاهر Windows 11 Fluent در ویندوز حفظ می‌شود.
- موتور تطبیقی دانلود سرعت اولیه را اندازه می‌گیرد و تعداد پارت مناسب را انتخاب می‌کند. نقشه بازه‌های بایتی برای Resume ذخیره می‌شود و در صورت پشتیبانی‌نکردن سرور از HTTP Range، دانلود تک‌اتصالی انجام می‌شود.
- پس از پایان موفق دانلود، پنجره جزئیات به دکمه‌های **Open** و **Close** تغییر می‌کند.

تعداد پارت‌ها در شروع دانلود انتخاب می‌شود و در حین انتقال تغییر نمی‌کند تا داده‌ها با هم تداخل نکنند و Resume قابل‌اعتماد بماند.

## دریافت نسخه ویندوز

لینک‌های پایدار زیر به آخرین انتشار GitHub متصل هستند:

- **[نسخه Portable ZIP — نسخه 6.40.2](https://github.com/meicamghe/FDMX/releases/download/v6.40.2/GNS-Downloader-Portable-Windows-x64.zip)** — فایل را استخراج و `GNS Downloader.exe` را اجرا کنید.
- **[نسخه Setup — نسخه 6.40.2](https://github.com/meicamghe/FDMX/releases/download/v6.40.2/GNS-Downloader-Setup.exe)** — برای نصب برنامه و ساخت میانبرها اجرا کنید.
- [مشاهده همه انتشارها در GitHub](https://github.com/meicamghe/FDMX/releases)

به‌روزرسانی درون‌برنامه‌ای برای نسخه نصب‌شده ویندوز، فایل Setup را دریافت می‌کند. نسخه Portable و اجرای مستقیم از سورس، صفحه انتشارها را باز می‌کنند تا ZIP جدید را دریافت و پوشه قبلی را جایگزین کنید.

Workflow ساخت ویندوز: [Build GNS Downloader Windows packages](https://github.com/meicamghe/FDMX/actions/workflows/build-fdmx-windows.yml). نسخه پایدار فعلی [v6.40.2](https://github.com/meicamghe/FDMX/releases/tag/v6.40.2) است. ساخت روی شاخه Artifact موقت تولید می‌کند و انتشار Tag نسخه، فایل‌های Release را منتشر می‌کند.

بهبود بعدی رابط آپدیتر شامل نمایش توضیحات نسخه پیش از دانلود، تأیید جداگانه دانلود و نصب و نمایش درصد/سرعت دانلود در [PR شماره ۱۸](https://github.com/meicamghe/FDMX/pull/18) در حال بررسی است و هنوز داخل نصب‌کننده منتشرشده 6.40.2 قرار ندارد.

## اجرای برنامه از سورس

Python **3.12** را نصب کنید و در پوشه پروژه اجرا کنید:

### لینوکس

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install PySide6-Essentials
python ubuntu.py
```

### ویندوز PowerShell

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PySide6-Essentials
python FDMX_v6_36.py
```

## ساخت بسته‌های ویندوز

ساخت فایل اجرایی ویندوز باید روی ویندوز انجام شود؛ PyInstaller ابزار Cross-Compile نیست. برای ساخت به Python 3.12، PySide6-Essentials، PyInstaller، Pillow و Inno Setup نیاز دارید. روش استاندارد ساخت و تست در Workflow گیت‌هاب تعریف شده است.

## افزونه مرورگر و حریم خصوصی

سورس افزونه‌های Chrome و Firefox در پوشه `browser-extensions/` قرار دارد. سرویس ارتباط دسکتاپ فقط روی 127.0.0.1:38471 گوش می‌دهد؛ آن را روی شبکه محلی یا اینترنت عمومی منتشر نکنید.

وظایف و تاریخچه دانلود در پوشه `.fdmx` داخل پروفایل کاربر ذخیره می‌شوند. لینک دانلود ممکن است توکن خصوصی داشته باشد؛ پیش از ارسال لاگ، اطلاعات حساس URL را حذف کنید.

## تست‌ها

```bash
python -m py_compile FDMX_v6_36.py ubuntu.py
python tests/test_gns_downloader_regressions.py
```

فایل‌های شماره‌دار قدیمی برای تاریخچه توسعه در مخزن باقی مانده‌اند؛ فایل مرجع برنامه فعلی `FDMX_v6_36.py` است.

پیش از توزیع مجدد سورس یا فایل‌های اجرایی، [اطلاعیه مجوز پروژه](../LICENSE-NOTICE.md) را مطالعه کنید.
