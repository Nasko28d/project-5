import os
import shutil
import tempfile
from pathlib import Path

import streamlit as st
import yt_dlp

st.set_page_config(page_title='YouTube Конвертор', page_icon='🎬', layout='centered')

st.markdown(
    """
    <style>
    .block-container {max-width: 720px; padding-top: 2rem;}
    .stButton>button {width: 100%; border-radius: 10px; font-weight: 600;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title('🎬 YouTube Конвертор')
st.caption('MP3 или MP4 директно от браузъра.')

CLIENT_SETS = [None, ['tv'], ['mweb']]
MAX_MB = 500  # защита на паметта на сървъра


def get_secret(name):
    try:
        return st.secrets.get(name)
    except Exception:
        return None


url = st.text_input('Линк към YouTube', placeholder='https://www.youtube.com/watch?v=...')

col1, col2 = st.columns(2)
with col1:
    fmt = st.radio('Формат', ['🎵 MP3', '🎥 MP4'], horizontal=True)
is_audio = fmt.startswith('🎵')
with col2:
    if is_audio:
        quality = st.select_slider('Качество (kbps)', options=[128, 192, 256, 320], value=192)
    else:
        quality = st.select_slider('Макс. резолюция', options=[360, 480, 720, 1080], value=720)

with st.expander('⚙️ Настройки'):
    cookies_upload = st.file_uploader('cookies.txt (по избор, Netscape формат)', type=['txt'])
    proxy_input = st.text_input(
        'Прокси (по избор)', placeholder='http://user:pass@host:port', type='password',
        help='Може да се зададе и като PROXY в Secrets на Streamlit Cloud.'
    )
    st.caption(f'yt-dlp версия: {yt_dlp.version.__version__}')

proxy = proxy_input.strip() or get_secret('PROXY')


def build_opts(folder, cookie_path, clients, hook):
    opts = {
        'outtmpl': os.path.join(folder, '%(title).120B.%(ext)s'),
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'retries': 3,
        'progress_hooks': [hook],
        'max_filesize': MAX_MB * 1024 * 1024,
    }
    if shutil.which('node'):
        opts['js_runtimes'] = {'node': {}}
    if cookie_path:
        opts['cookiefile'] = cookie_path
    if proxy:
        opts['proxy'] = proxy
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


if st.button('⬇️ Подготви файла', type='primary'):
    if not url.strip():
        st.warning('Въведи линк.')
    else:
        work = tempfile.mkdtemp()
        bar = st.progress(0.0, text='Стартиране...')
        errors = []
        result = None

        def hook(d):
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                if total:
                    pct = min(d['downloaded_bytes'] / total, 1.0)
                    bar.progress(pct, text=f'Изтегляне: {pct * 100:.0f}%')
            elif d['status'] == 'finished':
                bar.progress(1.0, text='Обработка...')

        try:
            cookie_path = None
            if cookies_upload is not None:
                cookie_path = os.path.join(work, 'cookies.txt')
                with open(cookie_path, 'wb') as f:
                    f.write(cookies_upload.getbuffer())

            for i, clients in enumerate(CLIENT_SETS):
                out = os.path.join(work, f'try_{i}')
                os.makedirs(out, exist_ok=True)
                try:
                    with yt_dlp.YoutubeDL(build_opts(out, cookie_path, clients, hook)) as ydl:
                        info = ydl.extract_info(url.strip(), download=True)
                    exts = ('.mp3',) if is_audio else ('.mp4', '.mkv', '.webm')
                    files = [p for p in Path(out).iterdir() if p.suffix.lower() in exts]
                    if files:
                        p = files[0]
                        result = (p.read_bytes(), p.name, info.get('title', p.stem))
                        break
                    errors.append('Файлът не е създаден (възможно е над лимита от '
                                  f'{MAX_MB} MB).')
                except Exception as e:
                    errors.append(f"[{', '.join(clients) if clients else 'по подразбиране'}] {e}")
        finally:
            shutil.rmtree(work, ignore_errors=True)

        if result:
            data, name, title = result
            bar.progress(1.0, text='Готово ✅')
            st.success(f'**{title}**')
            st.download_button(
                '💾 Изтегли файла',
                data=data,
                file_name=name,
                mime='audio/mpeg' if is_audio else 'video/mp4',
            )
        else:
            bar.progress(1.0, text='Неуспешно ❌')
            st.error('Не успях да изтегля файла.')
            with st.expander('Подробности'):
                st.code('\n\n'.join(errors))
            st.info('403 или „Sign in to confirm you’re not a bot“ значи, че YouTube '
                    'блокира IP адреса на сървъра. Помагат пресни cookies.txt или '
                    'жилищно прокси.')
