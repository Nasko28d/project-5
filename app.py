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

# Полета за въвеждане
url = st.text_input(
    'YouTube URL:', placeholder='https://youtube.com...'
)
format_choice = st.radio('Избери формат:', ['MP3 (Аудио)', 'MP4 (Видео)'])

# Опционално качване на cookies.txt при грешка 403
with st.expander('⚙️ Разширени настройки (ако дава грешка 403)'):
  uploaded_cookies = st.file_uploader(
      'Качи cookies.txt файл (по избор)', type=['txt']
  )


def process_video(video_url, is_audio, cookies_file=None):
  temp_dir = tempfile.mkdtemp()
  cookie_path = None

  try:
    if cookies_file is not None:
      cookie_path = os.path.join(temp_dir, 'cookies.txt')
      with open(cookie_path, 'wb') as f:
        f.write(cookies_file.getbuffer())

    # Базови настройки (без android/ios ограничение, за да работят всички формати с cookies)
    common_opts = {
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
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
    else:
      # Взима най-доброто налично видео и аудио и ги обединява в MP4 чрез FFmpeg
      ydl_opts = {
          **common_opts,
          'format': 'bestvideo+bestaudio/best',
          'merge_output_format': 'mp4',
      }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
      ydl.extract_info(video_url, download=True)

    downloaded_files = [
        f for f in os.listdir(temp_dir) if f != 'cookies.txt'
    ]

    if not downloaded_files:
      return None, None

    file_name = downloaded_files
    file_path = os.path.join(temp_dir, file_name)

    with open(file_path, 'rb') as f:
      file_bytes = f.read()

    return file_bytes, file_name

  finally:
    shutil.rmtree(temp_dir, ignore_errors=True)


# Бутон за стартиране
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
          st.error('Неуспешно генериране на файла. Провери дали линкът е публичен.')
      except Exception as e:
        st.error(f'Възникна грешка: {e}')
