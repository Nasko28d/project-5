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

url = st.text_input(
    'YouTube URL:', placeholder='https://www.youtube.com/watch?v=...'
)
format_choice = st.radio('Избери формат:', ['MP3 (Аудио)', 'MP4 (Видео)'])

with st.expander('⚙️ Разширени настройки (cookies.txt)', expanded=False):
    uploaded_cookies = st.file_uploader(
        'Качи cookies.txt файл (по избор)', type=['txt']
    )


def list_formats(video_url, base_opts):
    """Връща кратък списък с наличните формати (за диагностика)."""
    opts = {**base_opts, 'format': None, 'ignore_no_formats_error': True}
    opts.pop('format')
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
    lines = []
    for f in info.get('formats', []):
        lines.append(
            f"{f.get('format_id')} | {f.get('ext')} | "
            f"{f.get('resolution') or 'audio'} | "
            f"v:{f.get('vcodec')} a:{f.get('acodec')}"
        )
    return lines


def process_video(video_url, is_audio, cookies_file=None):
    temp_dir = tempfile.mkdtemp()
    cookie_path = None

    try:
        if cookies_file is not None:
            cookie_path = os.path.join(temp_dir, 'cookies.txt')
            with open(cookie_path, 'wb') as f:
                f.write(cookies_file.getbuffer())

        common_opts = {
            'outtmpl': os.path.join(temp_dir, '%(title).150B.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'js_runtimes': {'node': {}},
        }
        if cookie_path:
            common_opts['cookiefile'] = cookie_path

        if is_audio:
            ydl_opts = {
                **common_opts,
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            wanted_ext = '.mp3'
        else:
            ydl_opts = {
                **common_opts,
                'format': 'bv*+ba/b',
                'merge_output_format': 'mp4',
            }
            wanted_ext = '.mp4'

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(video_url, download=True)
        except Exception as e:
            # При грешка показваме какво реално връща YouTube
            try:
                formats = list_formats(video_url, common_opts)
                st.error(f'Грешка при изтегляне: {e}')
                st.write(f'Намерени формати: {len(formats)}')
                st.code('\n'.join(formats[:30]) or '(празен списък)')
            except Exception as e2:
                st.error(f'Грешка при изтегляне: {e}')
                st.error(f'Не успях и да взема списъка с формати: {e2}')
            return None, None

        downloaded_files = [
            f for f in os.listdir(temp_dir)
            if f.lower().endswith(wanted_ext)
        ]
        if not downloaded_files:
            return None, None

        file_name = downloaded_files[0]
        file_path = os.path.join(temp_dir, file_name)

        with open(file_path, 'rb') as f:
            file_bytes = f.read()

        return file_bytes, file_name

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if st.button('Подготви файла', type='primary'):
    if not url.strip():
        st.warning('Моля, въведи валиден YouTube линк.')
    else:
        with st.spinner('Изтегляне и обработка... Моля, изчакай.'):
            try:
                is_mp3 = format_choice.startswith('MP3')
                file_bytes, file_name = process_video(
                    url.strip(), is_mp3, uploaded_cookies
                )

                if file_bytes and file_name:
                    mime_type = 'audio/mpeg' if is_mp3 else 'video/mp4'
                    st.success(f'Готово! Файлът „{file_name}“ е подготвен.')
                    st.download_button(
                        label='⬇️ Изтегли файла на устройството си',
                        data=file_bytes,
                        file_name=file_name,
                        mime=mime_type,
                    )
                else:
                    st.error('Неуспешно генериране на файла.')
            except Exception as e:
                st.error(f'Възникна грешка: {e}')
