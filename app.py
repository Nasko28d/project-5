import os
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


def process_video(video_url, is_audio):
  # Създаваме временна директория, за да не пълним сървъра с файлове
  temp_dir = tempfile.mkdtemp()

  if is_audio:
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'quiet': True,
    }
  else:
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
        'quiet': True,
    }

  with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(video_url, download=True)
    # Намираме името на генерирания файл във временната папка
    downloaded_files = os.listdir(temp_dir)
    if not downloaded_files:
      return None, None
    file_path = os.path.join(temp_dir, downloaded_files[0])
    return file_path, downloaded_files[0]


# Бутон за стартиране
if st.button('Подготви файла', type='primary'):
  if not url:
    st.warning('Моля, въведи валиден YouTube линк.')
  else:
    with st.spinner('Обработка на видеото... Моля, изчакай.'):
      try:
        is_mp3 = format_choice.startswith('MP3')
        file_path, file_name = process_video(url, is_mp3)

        if file_path and os.path.exists(file_path):
          with open(file_path, 'rb') as f:
            file_bytes = f.read()

          mime_type = 'audio/mpeg' if is_mp3 else 'video/mp4'
          st.success('Файлът е готов!')

          # Бутон за реално сваляне от браузъра
          st.download_button(
              label=f'⬇️ Изтегли {file_name}',
              data=file_bytes,
              file_name=file_name,
              mime=mime_type,
          )
        else:
          st.error('Неуспешно генериране на файла.')
      except Exception as e:
        st.error(f'Възникна грешка: {e}')
