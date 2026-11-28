import os
import re
import shutil
import tempfile

import streamlit as st
import yt_dlp

st.set_page_config(
    page_title='YouTube към MP3/MP4', page_icon='🎬', layout='centered'
)

# ---------------------------------------------------------------- константи

CLIENT_SETS = [None, ['tv'], ['web_safari'], ['mweb'], ['android_vr']]

VIDEO_EXTS = ('.mp4', '.mkv', '.webm')
MIME_TYPES = {
    '.mp3': 'audio/mpeg',
    '.mp4': 'video/mp4',
    '.mkv': 'video/x-matroska',
    '.webm': 'video/webm',
}

# Грешки, при които няма смисъл да пробваме други клиенти
FATAL_MARKERS = (
    'private video',
    'video unavailable',
    'has been removed',
    'copyright',
    'members-only',
    'unsupported url',
    'is not a valid url',
    'live event will begin',
    'premieres in',
)

ANSI_RE = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

HAS_FFMPEG = shutil.which('ffmpeg') is not None
HAS_NODE = shutil.which('node') is not None


def clean_error(e):
    return ANSI_RE.sub('', str(e)).strip()


def is_fatal(msg):
    low = msg.lower()
    return any(m in low for m in FATAL_MARKERS)


def human_size(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024:
            return f'{n:.1f} {unit}'
        n /= 1024
    return f'{n:.1f} TB'


# ---------------------------------------------------------------- yt-dlp

def base_opts(cookie_source, cookie_path, proxy_url):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }
    if HAS_NODE:
        opts['js_runtimes'] = {'node': {}}
    if cookie_source in ('Firefox', 'Chrome', 'Edge'):
        opts['cookiesfrombrowser'] = (cookie_source.lower(),)
    elif cookie_path:
        opts['cookiefile'] = cookie_path
    if proxy_url:
        opts['proxy'] = proxy_url
    return opts


def build_opts(out_dir, is_audio, quality, cookie_source, cookie_path,
               proxy_url, clients, hook):
    opts = base_opts(cookie_source, cookie_path, proxy_url)
    opts.update({
        'outtmpl': os.path.join(out_dir, '%(title).150B.%(ext)s'),
        'retries': 5,
        'fragment_retries': 5,
        'restrictfilenames': False,
        'windowsfilenames': True,
        'progress_hooks': [hook],
    })
    if clients:
        opts['extractor_args'] = {'youtube': {'player_client': clients}}

    if is_audio:
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': quality,  # '128' / '192' / '320'
        }]
    else:
        h = quality  # '' = най-добро, иначе височина като '1080'
        cap = f'[height<={h}]' if h else ''
        opts['format'] = (
            f'bv*{cap}[vcodec^=avc1]+ba[acodec^=mp4a]/'
            f'bv*{cap}[ext=mp4]+ba[ext=m4a]/'
            f'bv*{cap}+ba/b{cap}/b'
        )
        opts['merge_output_format'] = 'mp4'
    return opts


def find_result(out_dir, is_audio):
    exts = ('.mp3',) if is_audio else VIDEO_EXTS
    files = [
        n for n in os.listdir(out_dir)
        if n.lower().endswith(exts) and not n.endswith('.part')
    ]
    if not files:
        return None
    files.sort(key=lambda n: os.path.getmtime(os.path.join(out_dir, n)),
               reverse=True)
    return files[0]


def make_hook(bar):
    def hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total:
                frac = min(d.get('downloaded_bytes', 0) / total, 1.0)
                speed = d.get('speed')
                extra = f' · {human_size(speed)}/s' if speed else ''
                bar.progress(frac, text=f'Изтегляне... {frac:.0%}{extra}')
        elif d['status'] == 'finished':
            bar.progress(1.0, text='Обработка (конвертиране/сливане)...')
    return hook


def process_video(video_url, is_audio, quality, cookie_source, cookies_file,
                  proxy_url, status, bar):
    base_dir = tempfile.mkdtemp()
    cookie_path = None
    errors = []
    hook = make_hook(bar)

    try:
        if cookies_file is not None:
            cookie_path = os.path.join(base_dir, 'cookies.txt')
            with open(cookie_path, 'wb') as f:
                f.write(cookies_file.getbuffer())

        for i, clients in enumerate(CLIENT_SETS):
            label = ', '.join(clients) if clients else 'по подразбиране'
            status.write(f'Опит {i + 1}/{len(CLIENT_SETS)}: клиент {label}...')
            bar.progress(0.0, text='Свързване...')

            out_dir = os.path.join(base_dir, f'try_{i}')
            os.makedirs(out_dir, exist_ok=True)

            try:
                opts = build_opts(out_dir, is_audio, quality, cookie_source,
                                  cookie_path, proxy_url, clients, hook)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.extract_info(video_url, download=True)

                file_name = find_result(out_dir, is_audio)
                if file_name:
                    with open(os.path.join(out_dir, file_name), 'rb') as f:
                        return f.read(), file_name, errors
                errors.append(f'[{label}] Не е създаден изходен файл.')
            except Exception as e:
                msg = clean_error(e)
                errors.append(f'[{label}] {msg}')
                if is_fatal(msg):
                    errors.append('Грешката е окончателна, спирам опитите.')
                    break

        return None, None, errors
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


# ---------------------------------------------------------------- интерфейс

st.title('🎬 YouTube Конвертор (MP3 / MP4)')
st.write('Постави YouTube линк по-долу и избери желания формат.')
st.caption(f'yt-dlp версия: {yt_dlp.version.__version__}')

if not HAS_FFMPEG:
    st.error('FFmpeg не е намерен. Без него MP3 и сливането на видео+аудио '
             'няма да работят. Инсталирай: `winget install ffmpeg`, после '
             'отвори нов cmd прозорец.')
if not HAS_NODE:
    st.warning('Node.js не е намерен. YouTube често връща грешки без него. '
               'Инсталирай: `winget install OpenJS.NodeJS.LTS`.')

url = st.text_input(
    'YouTube URL:', placeholder='https://www.youtube.com/watch?v=...'
)

col1, col2 = st.columns(2)
with col1:
    format_choice = st.radio('Формат:', ['MP3 (Аудио)', 'MP4 (Видео)'])
with col2:
    if format_choice.startswith('MP3'):
        quality_label = st.selectbox('Качество (kbps):',
                                     ['128', '192', '320'], index=1)
        quality = quality_label
    else:
        quality_label = st.selectbox(
            'Максимална резолюция:',
            ['Най-добра', '2160p', '1440p', '1080p', '720p', '480p', '360p'],
            index=0,
        )
        quality = '' if quality_label == 'Най-добра' else quality_label[:-1]

with st.expander('⚙️ Cookies и разширени настройки', expanded=False):
    cookie_source = st.selectbox(
        'Откъде да се вземат cookies?',
        ['Без cookies', 'Firefox', 'Chrome', 'Edge', 'Файл cookies.txt'],
        index=0,
        help='Нужни са само при грешка „Sign in to confirm you’re not a bot“ '
             'или за видеа с възрастово ограничение. Трябва да си влязъл в '
             'YouTube в избрания браузър. За Chrome/Edge затвори браузъра '
             'преди изтеглянето.',
    )
    uploaded_cookies = None
    if cookie_source == 'Файл cookies.txt':
        uploaded_cookies = st.file_uploader(
            'Качи cookies.txt (Netscape формат)', type=['txt']
        )
    proxy = st.text_input(
        'Прокси (по избор)', placeholder='http://user:pass@host:port'
    )

if st.button('Подготви файла', type='primary'):
    st.session_state.pop('result', None)
    st.session_state.pop('errors', None)

    if not url.strip():
        st.warning('Моля, въведи валиден YouTube линк.')
    elif cookie_source == 'Файл cookies.txt' and uploaded_cookies is None:
        st.warning('Качи cookies.txt или избери друг източник на cookies.')
    else:
        is_mp3 = format_choice.startswith('MP3')
        with st.status('Изтегляне и обработка... Моля, изчакай.',
                       expanded=True) as status:
            bar = st.progress(0.0, text='Стартиране...')
            try:
                file_bytes, file_name, errors = process_video(
                    url.strip(), is_mp3, quality, cookie_source,
                    uploaded_cookies, proxy.strip() or None, status, bar,
                )
            except Exception as e:
                file_bytes, file_name, errors = None, None, [clean_error(e)]

            if file_bytes and file_name:
                status.update(label='Готово!', state='complete')
            else:
                status.update(label='Неуспешно', state='error')

        if file_bytes and file_name:
            ext = os.path.splitext(file_name)[1].lower()
            st.session_state['result'] = {
                'data': file_bytes,
                'name': file_name,
                'mime': MIME_TYPES.get(ext, 'application/octet-stream'),
            }
        else:
            st.session_state['errors'] = errors

# Резултатът се пази в session_state, за да не изчезне след клик
# върху бутона за сваляне (Streamlit пуска скрипта наново).
result = st.session_state.get('result')
if result:
    st.success(f'Готово! Файлът „{result["name"]}“ '
               f'({human_size(len(result["data"]))}) е подготвен.')
    st.download_button(
        label='⬇️ Изтегли файла на устройството си',
        data=result['data'],
        file_name=result['name'],
        mime=result['mime'],
    )

errs = st.session_state.get('errors')
if errs is not None and not result:
    st.error('Неуспешно генериране на файла.')
    with st.expander('Подробности за грешките', expanded=True):
        st.code('\n\n'.join(errs) or '(няма данни)')
