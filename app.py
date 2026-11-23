import os
import shutil
import tempfile

import streamlit as st
import yt_dlp

st.set_page_config(
    page_title='YouTube към MP3/MP4', page_icon='🎬', layout='centered'
)

st.title('🎬 YouTube Конвертор (MP3 / MP4)')
st.write('Постави YouTube линк по-долу и избери желания формат.')
st.caption(f'yt-dlp версия: {yt_dlp.version.__version__}')

url = st.text_input(
    'YouTube URL:', placeholder='https://www.youtube.com/watch?v=...'
)
format_choice = st.radio('Избери формат:', ['MP3 (Аудио)', 'MP4 (Видео)'])

with st.expander('⚙️ Cookies и разширени настройки', expanded=True):
    cookie_source = st.selectbox(
        'Откъде да се вземат cookies?',
        ['Без cookies', 'Firefox', 'Chrome', 'Edge', 'Файл cookies.txt'],
        index=1,
        help='Трябва да си влязъл в YouTube в избрания браузър. '
             'За Chrome/Edge затвори браузъра преди изтеглянето.',
    )
    uploaded_cookies = None
    if cookie_source == 'Файл cookies.txt':
        uploaded_cookies = st.file_uploader(
            'Качи cookies.txt (Netscape формат)', type=['txt']
        )
    proxy = st.text_input(
        'Прокси (по избор)', placeholder='http://user:pass@host:port'
    )

CLIENT_SETS = [
    None,
    ['tv'],
    ['web_safari'],
    ['mweb'],
    ['android_vr'],
]

VIDEO_EXTS = ('.mp4', '.mkv', '.webm')
MIME_TYPES = {
    '.mp3': 'audio/mpeg',
    '.mp4': 'video/mp4',
    '.mkv': 'video/x-matroska',
    '.webm': 'video/webm',
}


def base_opts(cookie_source, cookie_path, proxy_url):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
    }
    if shutil.which('node'):
        opts['js_runtimes'] = {'node': {}}
    if cookie_source in ('Firefox', 'Chrome', 'Edge'):
        opts['cookiesfrombrowser'] = (cookie_source.lower(),)
    elif cookie_path:
        opts['cookiefile'] = cookie_path
    if proxy_url:
        opts['proxy'] = proxy_url
    return opts


def build_opts(out_dir, is_audio, cookie_source, cookie_path, proxy_url,
               clients):
    opts = base_opts(cookie_source, cookie_path, proxy_url)
    opts.update({
        'outtmpl': os.path.join(out_dir, '%(title).150B.%(ext)s'),
        'retries': 5,
        'fragment_retries': 5,
    })
    if clients:
        opts['extractor_args'] = {'youtube': {'player_client': clients}}

    if is_audio:
        opts['format'] = 'bestaudio/best'
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    else:
        opts['format'] = (
            'bv*[vcodec^=avc1]+ba[acodec^=mp4a]/'
            'bv*[ext=mp4]+ba[ext=m4a]/'
            'bv*+ba/b'
        )
        opts['merge_output_format'] = 'mp4'
    return opts


def find_result(out_dir, is_audio):
    exts = ('.mp3',) if is_audio else VIDEO_EXTS
    for name in sorted(os.listdir(out_dir)):
        if name.lower().endswith(exts):
            return name
    return None


def process_video(video_url, is_audio, cookie_source, cookies_file,
                  proxy_url, status):
    base_dir = tempfile.mkdtemp()
    cookie_path = None
    errors = []

    try:
        if cookies_file is not None:
            cookie_path = os.path.join(base_dir, 'cookies.txt')
            with open(cookie_path, 'wb') as f:
                f.write(cookies_file.getbuffer())

        for i, clients in enumerate(CLIENT_SETS):
            label = ', '.join(clients) if clients else 'по подразбиране'
            status.write(f'Опит {i + 1}/{len(CLIENT_SETS)}: клиент {label}...')

            out_dir = os.path.join(base_dir, f'try_{i}')
            os.makedirs(out_dir, exist_ok=True)

            try:
                opts = build_opts(out_dir, is_audio, cookie_source,
                                  cookie_path, proxy_url, clients)
                with yt_dlp.YoutubeDL(opts) as ydl:
                    ydl.extract_info(video_url, download=True)

                file_name = find_result(out_dir, is_audio)
                if file_name:
                    with open(os.path.join(out_dir, file_name), 'rb') as f:
                        return f.read(), file_name, errors
                errors.append(f'[{label}] Не е създаден изходен файл.')
            except Exception as e:
                errors.append(f'[{label}] {e}')

        return None, None, errors
    finally:
        shutil.rmtree(base_dir, ignore_errors=True)


if st.button('Подготви файла', type='primary'):
    if not url.strip():
        st.warning('Моля, въведи валиден YouTube линк.')
    elif cookie_source == 'Файл cookies.txt' and uploaded_cookies is None:
        st.warning('Качи cookies.txt или избери друг източник на cookies.')
    else:
        is_mp3 = format_choice.startswith('MP3')
        with st.status('Изтегляне и обработка... Моля, изчакай.',
                       expanded=True) as status:
            try:
                file_bytes, file_name, errors = process_video(
                    url.strip(), is_mp3, cookie_source, uploaded_cookies,
                    proxy.strip() or None, status,
                )
            except Exception as e:
                file_bytes, file_name, errors = None, None, [str(e)]

            if file_bytes and file_name:
                status.update(label='Готово!', state='complete')
            else:
                status.update(label='Неуспешно', state='error')

        if file_bytes and file_name:
            ext = os.path.splitext(file_name)[1].lower()
            st.success(f'Готово! Файлът „{file_name}“ е подготвен.')
            st.download_button(
                label='⬇️ Изтегли файла на устройството си',
                data=file_bytes,
                file_name=file_name,
                mime=MIME_TYPES.get(ext, 'application/octet-stream'),
            )
        else:
            st.error('Неуспешно генериране на файла. Всички опити се провалиха.')
            with st.expander('Подробности за грешките', expanded=True):
                st.code('\n\n'.join(errors) or '(няма данни)')
