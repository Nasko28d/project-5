import os
import shutil
import time
from pathlib import Path

import streamlit as st
import yt_dlp

st.set_page_config(page_title='YouTube Конвертор', page_icon='🎬', layout='centered')

st.markdown(
    """
    <style>
    .block-container {max-width: 760px; padding-top: 2rem;}
    .stButton>button {width: 100%; border-radius: 10px; font-weight: 600;}
    .title {font-size: 2.2rem; font-weight: 800; margin-bottom: 0;}
    .sub {color: #888; margin-top: 0;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<p class="title">🎬 YouTube Конвертор</p>', unsafe_allow_html=True)
st.markdown('<p class="sub">Свали видео (MP4) или аудио (MP3) с един клик.</p>',
            unsafe_allow_html=True)

DEFAULT_DIR = str(Path.home() / 'Downloads' / 'YouTube Конвертор')
CLIENT_SETS = [None, ['tv'], ['web_safari'], ['mweb'], ['android_vr']]

if 'history' not in st.session_state:
    st.session_state.history = []

# ---------- Вход ----------
urls_text = st.text_area(
    'Линк(ове) към YouTube',
    placeholder='https://www.youtube.com/watch?v=...\n(по един линк на ред)',
    height=100,
)

col1, col2 = st.columns(2)
with col1:
    fmt = st.radio('Формат', ['🎵 MP3 (аудио)', '🎥 MP4 (видео)'], horizontal=True)
is_audio = fmt.startswith('🎵')
with col2:
    if is_audio:
        quality = st.select_slider('Качество на звука (kbps)',
                                   options=[128, 192, 256, 320], value=192)
    else:
        quality = st.select_slider('Макс. резолюция',
                                   options=[360, 480, 720, 1080, 1440, 2160],
                                   value=1080)

with st.expander('⚙️ Настройки'):
    out_dir = st.text_input('Папка за запис', DEFAULT_DIR)
    cookie_source = st.selectbox(
        'Cookies от браузър (помага срещу блокиране)',
        ['Edge', 'Chrome', 'Firefox', 'Файл cookies.txt', 'Без cookies'],
        help='Трябва да си влязъл в YouTube в този браузър. '
             'За Chrome/Edge затвори браузъра преди изтегляне.',
    )
    cookies_upload = None
    if cookie_source == 'Файл cookies.txt':
        cookies_upload = st.file_uploader('cookies.txt', type=['txt'])
    st.caption(f'yt-dlp версия: {yt_dlp.version.__version__}')


# ---------- Логика ----------
def build_opts(folder, cookie_path, clients, hook):
    opts = {
        'outtmpl': os.path.join(folder, '%(title).150B.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'retries': 5,
        'fragment_retries': 5,
        'progress_hooks': [hook],
    }
    if shutil.which('node'):
        opts['js_runtimes'] = {'node': {}}
    if cookie_source in ('Edge', 'Chrome', 'Firefox'):
        opts['cookiesfrombrowser'] = (cookie_source.lower(),)
    elif cookie_path:
        opts['cookiefile'] = cookie_path
    if clients:
        opts['extractor_args'] = {'youtube': {'player_client': clients}}

    if is_audio:
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': str(quality),
        }]
    else:
        h = quality
        opts['format'] = (
            f'bv*[height<={h}][vcodec^=avc1]+ba[acodec^=mp4a]/'
            f'bv*[height<={h}]+ba/b[height<={h}]/b'
        )
        opts['merge_output_format'] = 'mp4'
    return opts


def download_one(url, folder, cookie_path, bar, label):
    def hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total:
                pct = min(d['downloaded_bytes'] / total, 1.0)
                speed = d.get('speed') or 0
                bar.progress(pct, text=f'{label}: {pct * 100:.0f}% '
                                       f'({speed / 1_048_576:.1f} MB/s)')
        elif d['status'] == 'finished':
            bar.progress(1.0, text=f'{label}: обработка...')

    errors = []
    for clients in CLIENT_SETS:
        try:
            started = time.time()
            with yt_dlp.YoutubeDL(build_opts(folder, cookie_path, clients, hook)) as ydl:
                info = ydl.extract_info(url, download=True)
            path = None
            try:
                path = info['requested_downloads'][0]['filepath']
            except Exception:
                files = [p for p in Path(folder).glob('*') if p.stat().st_mtime >= started]
                if files:
                    path = str(max(files, key=lambda p: p.stat().st_mtime))
            return info, path, errors
        except Exception as e:
            errors.append(f"[{', '.join(clients) if clients else 'по подразбиране'}] {e}")
    return None, None, errors


# ---------- Бутон ----------
if st.button('⬇️ Свали', type='primary'):
    urls = [u.strip() for u in urls_text.splitlines() if u.strip()]
    if not urls:
        st.warning('Въведи поне един линк.')
    elif cookie_source == 'Файл cookies.txt' and cookies_upload is None:
        st.warning('Качи cookies.txt или избери друг източник.')
    else:
        os.makedirs(out_dir, exist_ok=True)
        cookie_path = None
        if cookies_upload is not None:
            cookie_path = os.path.join(out_dir, '.cookies_tmp.txt')
            with open(cookie_path, 'wb') as f:
                f.write(cookies_upload.getbuffer())

        try:
            for i, url in enumerate(urls, 1):
                label = f'{i}/{len(urls)}'
                bar = st.progress(0.0, text=f'{label}: стартиране...')
                info, path, errors = download_one(url, out_dir, cookie_path, bar, label)
                if path:
                    bar.progress(1.0, text=f'{label}: готово ✅')
                    c1, c2 = st.columns([1, 3])
                    if info and info.get('thumbnail'):
                        c1.image(info['thumbnail'])
                    c2.success(f"**{info.get('title', os.path.basename(path))}**")
                    c2.caption(path)
                    st.session_state.history.append(path)
                else:
                    bar.progress(1.0, text=f'{label}: неуспешно ❌')
                    st.error(f'Неуспех за: {url}')
                    with st.expander('Подробности за грешката'):
                        st.code('\n\n'.join(errors))
        finally:
            if cookie_path and os.path.exists(cookie_path):
                os.remove(cookie_path)

# ---------- Папка и история ----------
if st.session_state.history:
    st.divider()
    st.subheader('Свалени в тази сесия')
    for p in reversed(st.session_state.history):
        st.write('•', os.path.basename(p))

if os.path.isdir(out_dir) and hasattr(os, 'startfile'):
    if st.button('📂 Отвори папката със свалените файлове'):
        os.startfile(out_dir)
