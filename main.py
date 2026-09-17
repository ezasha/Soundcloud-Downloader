from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from requests.adapters import HTTPAdapter
from mutagen.mp4 import MP4, MP4Cover
from urllib3.util.retry import Retry
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC
from dataclasses import dataclass
from urllib.parse import urljoin
from tkinter import filedialog
from queue import Queue
import threading
import datetime
import requests
import os.path
import zipfile
import json
import time
import re
import os


session = requests.Session()
replay = ""
CLIENT_ID = "Pb72ranhoyt6gw7hM7TkzUItXlMWSNSo"
album_artwork = []
outpout = None
REQUEST_TIMEOUT = (15, 180)
BATCH_DASHBOARD_MANAGER = None
CURRENT_BATCH_JOB = None

session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
})

retry = Retry(
    total=5,
    connect=5,
    read=5,
    status=5,
    backoff_factor=0.5,
    allowed_methods=None,
    status_forcelist=[429, 500, 502, 503, 504],
    raise_on_status=False,
)

adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
session.mount("https://", adapter)
session.mount("http://", adapter)


def safe_get(url, **kwargs):
    """Centralized requests wrapper with stronger retry behavior for slow CDN downloads."""
    timeout = kwargs.pop("timeout", REQUEST_TIMEOUT)
    stream = kwargs.pop("stream", False)
    response = session.get(url, timeout=timeout, stream=stream, **kwargs)
    response.raise_for_status()
    return response


def get_client_id():
    """A private function to get the api client_id (use if the tool no longer work)"""
    html = session.get("https://soundcloud.com", timeout=30).text
    scripts = re.findall(r'https://[^"]+sndcdn\.com/assets/[^"]+\.js', html)

    for js_url in scripts:
        js_code = session.get(js_url, timeout=20).text
        match = re.search(r'client_id:"([a-zA-Z0-9]{32})"', js_code)
        if match:
            return match.group(1)

    raise Exception("Impossible d'extraire le client_id.")


def ask(q):
    while True:
        a = input(f"{q} (Y/N): ").strip().lower()
        if a in ("y", "n"):
            break
        print("\033[31m" + "Please enter Y or N" + "\033[39m")
        time.sleep(0.5)
    return a

def ask_link():
    """A function to ask the soundcloud link"""
    link = input(f"Enter a soundcloud url: ").strip().lower()
    if not link.startswith("https://"):
        link = f"https://soundcloud.com/{link}"
    link.replace("m.soundcloud.com", "soundcloud.com")
    return link


def ask_outpout():
    """A function to ask the outpout folder"""
    outpout = filedialog.askdirectory(title="Sélectionnez le dossier d'outpout")
    if not outpout:
        print("\033[31m" + "No outpout folder selected" + "\033[39m")
        time.sleep(1)
        return 0
    return outpout


def get_json(url, auto="n"):
    """A function to get the JSON from the soundcloud api"""
    api = f"https://api-v2.soundcloud.com/resolve?url={url}&client_id={CLIENT_ID}"
    json = safe_get(api).json()
    if json == "{}":
        raise Exception(f"No result for {url}")
    kind = ask_json(json, auto)
    return json, kind


def get_user_id(url, auto='n'):
    """A variant of get_json to only get the user's id"""
    api = f"https://api-v2.soundcloud.com/resolve?url={url}&client_id={CLIENT_ID}"
    json = safe_get(api).json()
    if json == "{}":
        raise Exception(f"No result for {url}")
    ask_json(json, auto)
    return json["id"]


def get_track(id, auto='n', dl='y'):
    """A variant of get_json to only get the user's collection"""
    url = f"https://api-v2.soundcloud.com/tracks/{id}?client_id={CLIENT_ID}"
    json = safe_get(url).json()
    if json == "{}":
        raise Exception(f"No result for {url}")
    if dl == 'y':
        ask_json(json, auto)
    return json


def get_user_collection(url, auto='n'):
    """A variant of get_json to only get the user's collection"""
    user_id = get_user_id(url, auto)
    url = f"https://api-v2.soundcloud.com/users/{user_id}/tracks?client_id={CLIENT_ID}&limit=200"
    json = safe_get(url).json()
    if json == "{}":
        raise Exception(f"No result for {url}")
    ask_json(json, auto)
    return json["collection"]


def ask_json(json, auto="n"):
    """A function to ask if you want to save the json"""

    # 0. Get the today's date
    date = datetime.datetime.now()
    date = f"{date}".split(" ")[0]

    # 1. Detect the kind of the JSON
    if json.get("next_href"):
        q = f"Dump JSON for {json['collection'][0]['user']['permalink']}'s collection ?"
        filename = f"{json['collection'][0]['user']['permalink']} Collection [{date}].json"
        kind = 1
    elif json.get("kind") == "user":
        q = f"Dump JSON for the user {json['permalink']} ?"
        filename = f"{json['permalink']} User [{date}].json"
        kind = 2
    elif json.get("kind") == "track":
        q = f"Dump JSON for the track {json['permalink']} ?"
        filename = f"{json['permalink']} Track [{date}].json"
        kind = 3
    elif json.get("kind") == "playlist" and json.get("is_album") == True:
        q = f"Dump JSON for the album {json['permalink']} ?"
        filename = f"{json['permalink']} Album [{date}].json"
        kind = 4
    elif json.get("kind") == "playlist" and json.get("is_album") == False:
        q = f"Dump JSON for the playlist {json['permalink']} ?"
        filename = f"{json['permalink']} Playlist [{date}].json"
        kind = 5
    else:
        print("\033[31m" + "No JSON type detected." + "\033[39m")
        time.sleep(1)
        return 0

    # 2. Ask if you want to save the JSON
    if auto == "n":
        dl = ask(q)
    else:
        dl = "y"

    # 3. Download the dumped JSON
    if dl == "y":
        save_json(json, filename)

    return kind


def pick_transcoding(track):
    """A function to assemble every flux to format the mp3"""
    aac = None
    mp3 = None
    for t in track["media"]["transcodings"]:
        aac = t if t["preset"] == "aac_160k" else aac
        mp3 = t if t["format"]["protocol"] == "progressive" else mp3

    if mp3 == None:
        raise Exception("Aucun transcoding compatible trouvé.")
    return mp3, aac


def get_mp3_url(transcoding_url, client_id):
    """A function to get the final download link"""
    r = safe_get(f"{transcoding_url}?client_id={client_id}").json()
    if "url" in r:
        return r["url"]
    return None


def download_mp3(url, temp_path):
    """A function to save the extracted mp3"""
    with safe_get(url, stream=True, timeout=(20, 180)) as r:
        with open(temp_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)


def resolve_cover_url(json, kind):
    """Return the most relevant cover url for a track or user. Falls back to user avatar if track artwork is missing."""
    if kind == 2:
        return json.get("avatar_url")

    track_cover = json.get("artwork_url")
    if track_cover:
        return track_cover

    user = json.get("user") or {}
    avatar = user.get("avatar_url")
    if avatar:
        return avatar.replace("-large", "-original")
    return None


def ask_artwork(json, kind, auto="n"):
    # 1. Determine the filename
    if kind == 1:
        print("\033[31m" + "A collection doesn't have an artwork + \033[39m")
        return
    elif kind == 2:
        name = json["username"]
        if json.get("avatar_url") is None:
            print("Skip → no artwork")
            return
    elif kind in (3, 4, 5):
        name = json["title"]
        cover_url = resolve_cover_url(json, kind)
        if cover_url is None:
            print("Skip → no artwork")
            return
    else:
        print("\033[31m" + "No kind specified" + "\033[39m")
        return

    # 2. Ask for Artwork
    if auto == "n":
        dl = ask(f"Save artwork of {name} ({json['permalink']}) ?")
    elif auto == "y":
        dl = "y"
    elif auto == "t":
        dl = "n"

    global outpout
    if kind == 2:
        cover_url = json.get("avatar_url")
        cover_bytes = save_artwork(cover_url, f"_{name}", dl) if cover_url else None
    else:
        cover_url = resolve_cover_url(json, kind)
        cover_bytes = save_artwork(cover_url, name, dl) if cover_url else None

    # 3. Ask for Banner
    visuals = json.get("visuals", {})
    visuals_list = visuals.get("visuals", []) if visuals else None

    if visuals_list and visuals_list[0].get("visual_url") and kind in (2, 3):
        if auto == "n":
            dl = ask(f"Save banner of {name} ({json['permalink']}) ?")
        else:
            dl = "y"

        if dl == "y":
            name = f"_{name}_banner"
            save_artwork(json["visuals"]["visuals"][0]["visual_url"], name, "y")

    return cover_bytes


def save_artwork(artwork_url, name, dl="n"):
    """A function to extract the artwork from a json"""
    try:
        artwork_url = artwork_url.replace("-large", "-original")
    except:
        print("\033[31m" + "-large not detected" + "\033[39m")
        time.sleep(0.5)
    ext = artwork_url.split(".")[-1].lower()

    r = safe_get(artwork_url, stream=True, timeout=(20, 180))
    cover_bytes = b"".join(r.iter_content(chunk_size=65536))

    if cover_bytes == "not found: 403 Forbidden":
        print("\033[31m" + "403 forbidden" + "\033[39m")
        return
        
    cover_filename = f"{re.sub(r'[\\/:*?"<>|]', '', name)}.{ext}".lower()

    global outpout
    cover_path = os.path.join(outpout, cover_filename)

    if dl == "y":
        try:
            if not os.path.isfile(cover_path):
                with open(cover_path, "wb") as img:
                    img.write(cover_bytes)
                    print("\033[32m" + f"Téléchargé → {cover_filename}" + "\033[39m")
            else:
                print(f"Skip → {cover_filename} already exist")
        except Exception as e:
            print(
                "\033[31m"
                + f"An error occured while downloading cover: {e}"
                + "\033[39m"
            )
    return cover_bytes


def save_json(data, filename):
    """A function to save the extracted json"""
    global outpout
    outpout = ask_outpout() if not outpout else outpout
    if outpout == 0:
        return

    file_outpout = os.path.join(outpout, filename)
    if os.path.isfile(file_outpout):
        filename = f"{filename}+"
        file_outpout = os.path.join(outpout, filename)

    with open(file_outpout, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
        print("\033[32m" + f"Téléchargé → {filename}" + "\033[39m")


def apply_tags(audio_path, title, artist, date, cover_bytes, format):
    """A function to apply tags on the extracted audio"""
    # ===== MP3 =====
    if format == 'mp3':
        # Check for tags corruption
        try:
            audio = ID3(audio_path)
        except:
            audio = ID3()
            audio.save(audio_path)

        # Apply tags
        audio = EasyID3(audio_path)
        if title:
            audio["title"] = title
        if artist:
            audio["artist"] = artist
        if date:
            audio["date"] = date
        audio.save()

        # Apply cover if one
        if cover_bytes:
            audio = ID3(audio_path)
            audio.add(
                APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_bytes)
            )
        audio.save()

    elif format == 'm4a':
        audio = MP4(audio_path)

        if title:
            audio["\xa9nam"] = title
        if artist:
            audio["\xa9ART"] = artist
        if date:
            audio["\xa9day"] = date

        if cover_bytes:
            audio["covr"] = [
                MP4Cover(cover_bytes, imageformat=MP4Cover.FORMAT_JPEG)
            ]
        audio.save()
    
    else:
        print('apply tags cancelled -> unknowned format')
        return


def update_batch_progress(progress, status=None):
    global CURRENT_BATCH_JOB
    if CURRENT_BATCH_JOB is None:
        return
    CURRENT_BATCH_JOB.progress = max(CURRENT_BATCH_JOB.progress, int(progress))
    if status:
        CURRENT_BATCH_JOB.status = status


def download_soundcloud(url=None, auto="n", json=None, kind=0, aac="idk"):
    """A function to extract and download a track"""
    if not json:
        json, kind = get_json(url)
    if kind != 3:
        print("\033[31m" + "Resolve couldn't find a track." + "\033[39m")

    if outpout == 0:
        return

    global album_artwork
    artwork_url = resolve_cover_url(json, kind)
    if artwork_url and artwork_url in album_artwork:
        cover_bytes = ask_artwork(json, kind, "t")
        print(f"Skip → {artwork_url} already exist")
    else:
        cover_bytes = ask_artwork(json, kind, auto)
        if artwork_url:
            album_artwork.append(artwork_url)

    if aac == "idk":
        aac = ask("Download in AAC 160K ? (if no it's mp3 128kbps)")

    update_batch_progress(12, "downloading")

    if aac == "y":
        format = 'm4a'
        temp_folder = outpout if outpout else ask_outpout()
        if temp_folder == 0:
            return
        final_path = os.path.join(
            temp_folder,
            f"{re.sub(r'[\/:*?"<>|]', '', json['title'])}.m4a",
        )
        if not os.path.isfile(final_path):
            transcoding_mp3, transcoding_aac = pick_transcoding(json)
            for attempt in range(1, 4):
                try:
                    if transcoding_aac is None:
                        raise Exception("AAC transcoding missing")
                    playlist_url = get_mp3_url(transcoding_aac["url"], CLIENT_ID)
                    update_batch_progress(25 + attempt * 10, "downloading")
                    download_hls_with_ffmpeg(playlist_url, final_path)
                    safe_title = re.sub(r'[\\/:*?"<>|]', '', json["title"])
                    print("\033[32m" + f"Téléchargé → {safe_title}.m4a" + "\033[39m")
                    break
                except Exception as e:
                    print(f"\033[33m[AAC retry {attempt}/3] {json['title']}: {e}\033[39m")
                    if attempt < 3:
                        time.sleep(1)
                        continue
                    print("Direct HLS download failed, downloading mp3:", e)
                    format = 'mp3'
                    temp_path = f"{json['permalink']}.mp3"

                    final_path = f"{outpout}/{re.sub(r'[\/:*?"<>|]', '', json['title'])}.mp3"

                    if not os.path.isfile(final_path):
                        mp3_url = get_mp3_url(transcoding_mp3["url"], CLIENT_ID)
                        update_batch_progress(55, "downloading")
                        download_mp3(mp3_url, temp_path)
                        update_batch_progress(82, "downloading")
                        os.rename(temp_path, final_path)
                        print("\033[32m" + f'Téléchargé → {json["title"]}.mp3' + "\033[39m")
                    else:
                        print(f'Skip → {json["title"]}.mp3 already exist')
                    break
        else:
            safe_title = re.sub(r'[\\/:*?"<>|]', '', json["title"])
            print(f"Skip → {safe_title}.m4a already exist")
    else:
        format = 'mp3'
        temp_path = f"{json['permalink']}.mp3"

        final_path = f"{outpout}/{re.sub(r'[\/:*?"<>|]', '', json['title'])}.mp3"

        if not os.path.isfile(final_path):
            transcoding_mp3, transcoding_aac = pick_transcoding(json)
            mp3_url = get_mp3_url(transcoding_mp3["url"], CLIENT_ID)
            update_batch_progress(45, "downloading")
            download_mp3(mp3_url, temp_path)
            update_batch_progress(80, "downloading")
            os.rename(temp_path, final_path)
            print("\033[32m" + f'Téléchargé → {json["title"]}.mp3' + "\033[39m")
        else:
            print(f'Skip → {json["title"]}.mp3 already exist')

    update_batch_progress(90, "downloading")
    apply_tags(
        final_path,
        title=json["title"],
        artist=json["user"]["username"],
        date=json["display_date"].split("-")[0],
        cover_bytes=cover_bytes,
        format=format,
    )
    update_batch_progress(100, "done")



# =====================
# ===== TEST 160K =====
# =====================
def extract_m4s_segments(m3u8_text, playlist_url):
    init_file = None
    segments = []
    base_url = playlist_url.rsplit("/", 1)[0] + "/"

    map_match = re.search(r'EXT-X-MAP:URI=["\']([^"\']+)["\']', m3u8_text)
    if map_match:
        init_file = urljoin(base_url, map_match.group(1))

    regex_matches = re.findall(r'(?:https?://|/)[^\s"\'<>]+\.m4s(?:\?[^\s"\'<>]+)?', m3u8_text)
    if regex_matches:
        for match in regex_matches:
            segments.append(urljoin(base_url, match))
    else:
        for line in m3u8_text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if ".m4s" in stripped:
                segments.append(urljoin(base_url, stripped))

    return init_file, segments

def download_m4s(init_url, segments, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    paths = []

    # init.mp4
    init_path = os.path.join(output_dir, "init.mp4")
    init_data = safe_get(init_url, timeout=(20, 180)).content
    with open(init_path, "wb") as f:
        f.write(init_data)
    paths.append(init_path)

    # segments
    for i, seg_url in enumerate(segments):
        seg_path = os.path.join(output_dir, f"seg_{i}.m4s")
        seg_data = safe_get(seg_url, timeout=(20, 180)).content
        with open(seg_path, "wb") as f:
            f.write(seg_data)
        paths.append(seg_path)

    return paths

def create_concat_list(paths, list_path):
    with open(list_path, "w", encoding="utf-8") as f:
        for p in paths:
            norm_path = os.path.abspath(p).replace("\\", "/")
            f.write(f"file '{norm_path}'\n")

import subprocess

FFMPEG_PATH = r"C:\Users\chksh\Downloads\ffmpeg-2026-05-28-git-7b46c6a2a3-essentials_build\bin\ffmpeg.exe"

def download_hls_with_ffmpeg(playlist_url, output_path, retries=3):
    headers = (
        "User-Agent: Mozilla/5.0 (Linux; Android 10; SM-G973F) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36\r\n"
        "Accept: */*\r\n"
        "Accept-Language: en-US,en;q=0.9\r\n"
        "Referer: https://soundcloud.com/\r\n"
    )

    for attempt in range(1, retries + 1):
        cmd = [
            FFMPEG_PATH,
            "-y",
            "-timeout", "30000000",
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-headers", headers,
            "-i", playlist_url,
            "-vn",
            "-c", "copy",
            os.path.abspath(output_path),
        ]

        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if result.returncode == 0:
            print(result.stderr.decode())
            return

        message = result.stderr.decode(errors="ignore")
        print(f"\033[33m[ffmpeg attempt {attempt}/{retries}] {playlist_url}\n{message[:400]}\033[39m")
        if attempt < retries:
            time.sleep(1)

    raise Exception("FFmpeg a échoué pendant le download direct HLS.")


def remux_fmp4(paths, output_path):
    list_path = os.path.join(os.path.dirname(os.path.abspath(output_path)), "concat_list.txt")
    create_concat_list(paths, list_path)

    cmd = [
        FFMPEG_PATH,
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        os.path.abspath(output_path),
    ]

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        print(result.stderr.decode())
        raise Exception("FFmpeg a échoué pendant le remux HLS.")
    print(result.stderr.decode())

def download_hls_playlist(url):
    r = safe_get(url, timeout=(15, 180))

    content_type = r.headers.get("content-type", "").lower()
    if "application/json" in content_type or r.text.lstrip().startswith("{"):
        payload = r.json()
        if isinstance(payload, dict) and payload.get("url"):
            r = safe_get(payload["url"], timeout=(15, 180))

    print('r.text done')
    return r.text


def create_batch_zip(output_dir, zip_name=None):
    """Package the downloaded batch into a zip archive."""
    if not output_dir or not os.path.isdir(output_dir):
        return None

    if zip_name is None:
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = f"download_batch_{stamp}.zip"

    zip_path = os.path.join(output_dir, zip_name)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for root, _, files in os.walk(output_dir):
            for filename in files:
                if filename == zip_name:
                    continue
                if filename.lower().endswith(".tmp"):
                    continue
                full_path = os.path.join(root, filename)
                arcname = os.path.relpath(full_path, output_dir)
                archive.write(full_path, arcname)

    print(f"\033[32m[zip] Archive créée → {zip_path}\033[39m")
    return zip_path


@dataclass
class BatchDownloadJob:
    """A single work item for an album/user batch download."""
    id: int
    title: str
    track_json: dict
    auto: str = "y"
    aac: str = "n"
    status: str = "queued"
    progress: int = 0
    error: str = ""


class BatchDashboardHandler(BaseHTTPRequestHandler):
    manager = None

    def do_GET(self):
        if self.path == "/api/status":
            body = json.dumps(self.manager.snapshot()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            while True:
                try:
                    payload = json.dumps(self.manager.snapshot())
                    self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(1)
                except (BrokenPipeError, ConnectionResetError):
                    break
            return

        html = self.manager.render_dashboard_html()
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        return


class BatchDownloadManager:
    """Threaded batch downloader with a bounded worker pool and live dashboard."""

    def __init__(self, max_workers=5, auto="y", aac="n", dashboard_port=8765):
        self.max_workers = max_workers
        self.auto = auto
        self.aac = aac
        self.jobs = []
        self.queue = Queue()
        self.lock = threading.Lock()
        self.dashboard_port = dashboard_port
        self.dashboard_server = None
        self.worker_map = {}

    def snapshot(self):
        jobs = []
        for job in self.jobs:
            jobs.append({
                "id": job.id,
                "title": job.title,
                "status": job.status,
                "progress": job.progress,
                "error": job.error,
            })

        workers = []
        for name, info in self.worker_map.items():
            workers.append({
                "name": name,
                "status": info.get("status", "idle"),
                "job": info.get("job", "")
            })

        return {
            "total": len(self.jobs),
            "done": sum(1 for j in self.jobs if j.status == "done"),
            "failed": sum(1 for j in self.jobs if j.status == "failed"),
            "running": sum(1 for j in self.jobs if j.status == "downloading"),
            "queued": sum(1 for j in self.jobs if j.status == "queued"),
            "jobs": jobs,
            "workers": workers,
        }

    def render_dashboard_html(self):
        state = self.snapshot()
        rows = []
        for job in state["jobs"]:
            rows.append(
                "<tr>"
                f"<td>{job['id']}</td>"
                f"<td>{job['title']}</td>"
                f"<td>{job['status']}</td>"
                f"<td>{job['progress']}%</td>"
                f"<td>{job['error'] or '-'}</td>"
                "</tr>"
            )

        workers_rows = []
        if not state["workers"]:
            workers_rows.append("<tr><td colspan='3'>Aucun worker actif</td></tr>")
        for worker in state["workers"]:
            workers_rows.append(
                "<tr>"
                f"<td>{worker['name']}</td>"
                f"<td>{worker['status']}</td>"
                f"<td>{worker['job']}</td>"
                "</tr>"
            )

        return f"""
        <!doctype html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>SoundCloud Batch Dashboard</title>
            <style>
                body {{ font-family: Arial, sans-serif; background: #111827; color: #e5e7eb; margin: 24px; }}
                h1 {{ margin-bottom: 12px; }}
                .stats {{ display: flex; gap: 16px; margin-bottom: 20px; flex-wrap: wrap; }}
                .card {{ background: #1f2937; border-radius: 8px; padding: 12px 18px; min-width: 120px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
                th, td {{ border: 1px solid #374151; padding: 8px 10px; text-align: left; }}
                th {{ background: #111827; }}
                .ok {{ color: #4ade80; }}
                .warn {{ color: #fbbf24; }}
                .bad {{ color: #f87171; }}
            </style>
        </head>
        <body>
            <h1>SoundCloud Batch Dashboard</h1>
            <div class="stats">
                <div class="card"><strong>Total</strong><br>{state['total']}</div>
                <div class="card"><strong>Done</strong><br>{state['done']}</div>
                <div class="card"><strong>Running</strong><br>{state['running']}</div>
                <div class="card"><strong>Queued</strong><br>{state['queued']}</div>
                <div class="card"><strong>Failed</strong><br>{state['failed']}</div>
            </div>

            <h2>Workers</h2>
            <table>
                <tr><th>Worker</th><th>Status</th><th>Current job</th></tr>
                {''.join(workers_rows)}
            </table>

            <h2>Jobs</h2>
            <table>
                <tr><th>#</th><th>Title</th><th>Status</th><th>Progress</th><th>Error</th></tr>
                {''.join(rows)}
            </table>

            <script>
                const es = new EventSource('/events');
                es.onmessage = function(event) {{
                    const state = JSON.parse(event.data);
                    const rows = state.jobs.map(job => `
                        <tr>
                            <td>${{job.id}}</td>
                            <td>${{job.title}}</td>
                            <td>${{job.status}}</td>
                            <td>${{job.progress}}%</td>
                            <td>${{job.error || '-'}}</td>
                        </tr>`).join('');
                    document.querySelector('table:nth-of-type(2)').innerHTML = `
                        <tr><th>#</th><th>Title</th><th>Status</th><th>Progress</th><th>Error</th></tr>
                        ${{rows}}
                    `;
                    const workers = state.workers.map(w => `
                        <tr>
                            <td>${{w.name}}</td>
                            <td>${{w.status}}</td>
                            <td>${{w.job}}</td>
                        </tr>`).join('');
                    document.querySelector('table:nth-of-type(1)').innerHTML = `
                        <tr><th>Worker</th><th>Status</th><th>Current job</th></tr>
                        ${{workers}}
                    `;
                    const cards = document.querySelectorAll('.card');
                    cards[0].innerHTML = '<strong>Total</strong><br>' + state.total;
                    cards[1].innerHTML = '<strong>Done</strong><br>' + state.done;
                    cards[2].innerHTML = '<strong>Running</strong><br>' + state.running;
                    cards[3].innerHTML = '<strong>Queued</strong><br>' + state.queued;
                    cards[4].innerHTML = '<strong>Failed</strong><br>' + state.failed;
                }};
            </script>
        </body>
        </html>
        """

    def enqueue_tracks(self, tracks):
        self.jobs = []
        for i, track in enumerate(tracks, start=1):
            job = BatchDownloadJob(
                id=i,
                title=track.get("title", f"Track {i}"),
                track_json=track,
                auto=self.auto,
                aac=self.aac,
            )
            self.jobs.append(job)
            self.queue.put(job)

    def _set_job_status(self, job, status, progress=None, error=""):
        with self.lock:
            job.status = status
            if progress is not None:
                job.progress = progress
            if error:
                job.error = error

    def _worker(self):
        worker_name = threading.current_thread().name
        self.worker_map[worker_name] = {"status": "idle", "job": ""}

        while True:
            job = self.queue.get()
            if job is None:
                self.queue.task_done()
                self.worker_map[worker_name] = {"status": "idle", "job": ""}
                break

            try:
                self.worker_map[worker_name] = {"status": "downloading", "job": job.title}
                self._set_job_status(job, "downloading", 0)
                global CURRENT_BATCH_JOB
                CURRENT_BATCH_JOB = job
                download_soundcloud(auto=job.auto, json=job.track_json, kind=3, aac=job.aac)
                if job.status != "failed":
                    self._set_job_status(job, "done", 100)
                    self.worker_map[worker_name] = {"status": "idle", "job": ""}
                else:
                    self.worker_map[worker_name] = {"status": "idle", "job": ""}
            except Exception as exc:
                self._set_job_status(job, "failed", 0, str(exc))
                self.worker_map[worker_name] = {"status": "idle", "job": ""}
                print(f"\033[31m[batch][{job.title}] failed: {exc}\033[39m")
            finally:
                CURRENT_BATCH_JOB = None
                self.queue.task_done()

    def start_dashboard(self):
        BatchDashboardHandler.manager = self
        self.dashboard_server = ThreadingHTTPServer(("127.0.0.1", self.dashboard_port), BatchDashboardHandler)
        threading.Thread(target=self.dashboard_server.serve_forever, daemon=True).start()
        print(f"\033[32m[dashboard] http://127.0.0.1:{self.dashboard_port}\033[39m")

    def stop_dashboard(self):
        if self.dashboard_server is not None:
            self.dashboard_server.shutdown()
            self.dashboard_server.server_close()
            self.dashboard_server = None

    def render_status(self):
        total = len(self.jobs)
        if total == 0:
            print("\033[36m[batch] no jobs queued\033[39m")
            return

        done = sum(1 for j in self.jobs if j.status == "done")
        failed = sum(1 for j in self.jobs if j.status == "failed")
        running = sum(1 for j in self.jobs if j.status == "downloading")
        queued = sum(1 for j in self.jobs if j.status == "queued")

        print("\n\033[35m=== Batch download status ===\033[39m")
        print(f"\033[36mProgress: {done}/{total} done | {running} running | {queued} queued | {failed} failed\033[39m")

        for job in self.jobs[:12]:
            color = "\033[32m" if job.status == "done" else "\033[33m" if job.status == "downloading" else "\033[31m" if job.status == "failed" else "\033[37m"
            print(f"{color}#{job.id:02d} {job.title[:26]:<26} {job.status:<10} {job.progress:>3}%\033[39m")

        if total > 12:
            print(f"\033[90m... plus {total - 12} titres dans la file\033[39m")

    def start(self, live=False, dashboard=True):
        if dashboard:
            self.start_dashboard()

        workers = [
            threading.Thread(target=self._worker, daemon=True, name=f"Worker-{i}")
            for i in range(1, min(self.max_workers, max(1, len(self.jobs))) + 1)
        ]

        for worker in workers:
            worker.start()

        if live:
            while True:
                if all(j.status in ("done", "failed") for j in self.jobs):
                    break
                self.render_status()
                time.sleep(0.8)

        self.queue.join()
        for _ in workers:
            self.queue.put(None)
        for worker in workers:
            worker.join(timeout=5)

        if live:
            self.render_status()

        if dashboard:
            self.stop_dashboard()

        return self.jobs


def ensure_dashboard_manager():
    global BATCH_DASHBOARD_MANAGER
    if BATCH_DASHBOARD_MANAGER is None:
        BATCH_DASHBOARD_MANAGER = BatchDownloadManager(max_workers=5, auto="y", aac="n", dashboard_port=8765)
        BATCH_DASHBOARD_MANAGER.start_dashboard()
    return BATCH_DASHBOARD_MANAGER


def batch_download_collection(tracks, auto="y", aac="n", max_workers=5):
    """Convenience wrapper to process a collection via a bounded queue and zip the result."""
    manager = ensure_dashboard_manager()
    manager.max_workers = max_workers
    manager.auto = auto
    manager.aac = aac
    manager.jobs = []
    manager.worker_map = {}
    manager.queue = Queue()
    manager.enqueue_tracks(tracks)
    manager.start(live=True, dashboard=False)

    if outpout:
        zip_path = create_batch_zip(outpout)
        if zip_path:
            print(f"\033[32m[batch] Tout est prêt dans le zip final: {zip_path}\033[39m")
    return manager.jobs


def mode_case1():
    """Option 1 to extract mp3 from a track, playlist or album"""
    url = ask_link()
    json, kind = get_json(url)
    global outpout
    if kind == 1:
        print("\033[31m" + "Couldn\'t handle a Collection from here (choose option 2)." + "\033[39m")
        time.sleep(1)
        return
    elif kind == 2:
        print("\033[31m" + "Couldn\'t find an mp3 from the given link." + "\033[39m")
        time.sleep(1)
        return
    elif kind == 3:
        auto = ask("Download everything (mp3, cover) ?")
        outpout = None
        download_soundcloud(url=url, auto=auto, json=json, kind=kind)
    elif kind in (4, 5):
        auto = ask("Download everything (mp3, cover) ?")
        dump_json = ask("Ask to download JSON dump ?")
        same_outpout = ask("Same outpout for everything ?")
        if same_outpout == "y":
            outpout = ask_outpout()
            if outpout == 0:
                return
        else:
            outpout = None
        
        print(f"Found {len(json['tracks'])} tracks.")

        global album_artwork
        cover_bytes = ask_artwork(json, kind, auto)
        if cover_bytes != "not found: 403 Forbidden":
            album_artwork.append(json['artwork_url'])

        if auto == "y":
            aac = ask("Download everything in AAC 160K ? (if no it\'s mp3 128kbps)")
            batch_download_collection(json["tracks"], auto="y", aac=aac, max_workers=5)
            return
                
        for track in json['tracks']:
            json = get_track(track['id'], auto, dump_json)

            if auto == "n":
                dl = ask(f"Download the track {json['title']} ?")
                if dl == "y":
                    download_soundcloud(json=json, kind=3)
            else:
                download_soundcloud(auto=auto, json=json, kind=3)
            if json['artwork_url'] not in album_artwork:
                album_artwork.append(json['artwork_url'])
            time.sleep(0.5)
    elif kind == 0:
        print("\033[31m" + "Couldn\'t resolve the given link." + "\033[39m")
        time.sleep(1)
        return


def mode_case2():
    """Option 2 to extract an entire collection from a user"""
    link = ask_link()
    auto = ask("Download everything (mp3, cover) ?")
    aac = ask("Download everything in AAC 160K ? (if no it\'s mp3 128kbps)")
    same_outpout = ask("Same outpout for everything ?")

    if same_outpout == "y":
        global outpout
        outpout = ask_outpout()
        if outpout == 0:
            return

    collection = get_user_collection(link, auto)

    global album_artwork
    print(f"Found {len(collection)} tracks.")

    if auto == "y":
        batch_download_collection(collection, auto="y", aac=aac, max_workers=5)
        for t in collection:
            if t.get('artwork_url') not in album_artwork:
                album_artwork.append(t.get('artwork_url'))
        return

    for t in collection:
        link = t["permalink_url"]

        print(f"\nTrack: {t['title']}")

        if auto == "n":
            dl = ask("Download this track ?")
            if dl == "y":
                download_soundcloud(json=t, kind=3, aac=aac)
        else:
            download_soundcloud(auto=auto, json=t, kind=3, aac=aac)
        if t['artwork_url'] not in album_artwork:
            album_artwork.append(t['artwork_url'])


def mode_case3():
    """Option 3 to extract JSON and visuals from an url"""
    url = ask_link()
    json, kind = get_json(url, "y")
    ask_artwork(json, kind)


def menu():
    """Global menu to select from available options"""
    global replay, outpout, album_artwork
    album_artwork = []
    outpout = None
    print(f"\n\nClient ID: {CLIENT_ID}")
    print("Dashboard: http://127.0.0.1:8765/")
    print("+-------------------------------------------------+")
    print("| Choisis le mode:                                |")
    print("|  " + "\033[36m" + "E" + "\033[39m" + " = exit                                       |")
    if replay != "":
        print("|  " + "\033[36m" + "R" + "\033[39m" + f" = Dernier mode ({replay})                           |")
    print("|  " + "\033[36m" + "1" + "\033[39m" + " = [MP3] track, playlist, album               |")
    print("|  " + "\033[36m" + "2" + "\033[39m" + " = [MP3] user                                 |")
    print("|  " + "\033[36m" + "3" + "\033[39m" + " = [JSON] track, playlist album, user         |")
    print("+-------------------------------------------------+\n")
    while True:
        choice = input("Tape E, R, 1, 2 ou 3: ").strip().lower() if replay != "" else input("Tape E, 1, 2 ou 3: ").strip().lower()            
        if choice == "e":
            exit()
        if choice == "r":
            choice = replay
        if choice == "1":
            replay = "1"
            return mode_case1()
        if choice == "2":
            replay = "2"
            return mode_case2()
        if choice == "3":
            replay = "3"
            return mode_case3()
        (
            print(
                "\033[31m"
                + "Entrée invalide. Merci de taper [R], 1, 2 ou 3.\n"
                + "\033[39m"
            )
            if replay != ""
            else print(
                "\033[31m"
                + "Entrée invalide. Merci de taper 1, 2 ou 3.\n"
                + "\033[39m"
            )
        )
        time.sleep(1)


if __name__ == "__main__":
    print(
        "\033[35m"
        + " █████╗ ███████╗██╗  ██╗ █████╗ ██████╗  ██████╗██╗  ██╗██╗██╗   ██╗███████╗███████╗\n"
        + "██╔══██╗██╔════╝██║  ██║██╔══██╗██╔══██╗██╔════╝██║  ██║██║██║   ██║██╔════╝██╔════╝\n"
        + "███████║███████╗███████║███████║██████╔╝██║     ███████║██║██║   ██║█████╗  ███████╗\n"
        + "██╔══██║╚════██║██╔══██║██╔══██║██╔══██╗██║     ██╔══██║██║╚██╗ ██╔╝██╔══╝  ╚════██║\n"
        + "██║  ██║███████║██║  ██║██║  ██║██║  ██║╚██████╗██║  ██║██║ ╚████╔╝ ███████╗███████║\n"
        + "╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝  ╚══════╝╚══════╝\n\n"
        + "███████╗ ██████╗     █████╗ ██████╗  ██████╗██╗  ██╗██╗██╗   ██╗███████╗██████╗     \n"
        + "██╔════╝██╔════╝    ██╔══██╗██╔══██╗██╔════╝██║  ██║██║██║   ██║██╔════╝██╔══██╗    \n"
        + "███████╗██║         ███████║██████╔╝██║     ███████║██║██║   ██║█████╗  ██████╔╝    \n"
        + "╚════██║██║         ██╔══██║██╔══██╗██║     ██╔══██║██║╚██╗ ██╔╝██╔══╝  ██╔══██╗    \n"
        + "███████║╚██████╗    ██║  ██║██║  ██║╚██████╗██║  ██║██║ ╚████╔╝ ███████╗██║  ██║    \n"
        + "╚══════╝ ╚═════╝    ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚═╝  ╚═══╝  ╚══════╝╚═╝  ╚═╝    "
        + "\033[39m"
    )

    if CLIENT_ID == "":
        try:
            CLIENT_ID = get_client_id()
        except:
            CLIENT_ID = "O7atZypwLvuWSY9hWnnQ3vrLTHH7wqMe"
    while True:
        if os.path.isfile("temp_download.mp3"):
            os.remove("temp_download.mp3")
        menu()
