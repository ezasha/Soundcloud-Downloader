from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC
from tkinter import filedialog
import datetime
import requests
import os.path
import json
import time
import re
import os

session = requests.Session()
replay = ""
CLIENT_ID = "O7atZypwLvuWSY9hWnnQ3vrLTHH7wqMe"
album_artwork = []
outpout = None

session.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://soundcloud.com/",
    }
)


def get_client_id():
    """A private function to get the api client_id (use if the tool no longer work)"""
    html = session.get("https://soundcloud.com").text
    scripts = re.findall(r'https://[^"]+sndcdn\.com/assets/[^"]+\.js', html)

    for js_url in scripts:
        js_code = session.get(js_url).text
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
    json = session.get(api).json()
    if json == "{}":
        raise Exception(f"No result for {url}")
    kind = ask_json(json, auto)
    return json, kind


def get_user_id(url, auto='n'):
    """A variant of get_json to only get the user's id"""
    api = f"https://api-v2.soundcloud.com/resolve?url={url}&client_id={CLIENT_ID}"
    json = session.get(api).json()
    if json == "{}":
        raise Exception(f"No result for {url}")
    ask_json(json, auto)
    return json["id"]


def get_track(id, auto='n', dl='y'):
    """A variant of get_json to only get the user's collection"""
    url = f"https://api-v2.soundcloud.com/tracks/{id}?client_id={CLIENT_ID}"
    json = session.get(url).json()
    if json == "{}":
        raise Exception(f"No result for {url}")
    if dl == 'y':
        ask_json(json, auto)
    return json


def get_user_collection(url, auto='n'):
    """A variant of get_json to only get the user's collection"""
    user_id = get_user_id(url, auto)
    url = f"https://api-v2.soundcloud.com/users/{user_id}/tracks?client_id={CLIENT_ID}&limit=200"
    json = session.get(url).json()
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
    for t in track["media"]["transcodings"]:
        if t["format"]["protocol"] == "progressive":
            return t
    for t in track["media"]["transcodings"]:
        if t["format"]["protocol"] == "hls":
            return t
    raise Exception("Aucun transcoding compatible trouvé.")


def get_mp3_url(transcoding_url, client_id):
    """A function to get the final download link"""
    r = session.get(f"{transcoding_url}?client_id={client_id}").json()
    if "url" in r:
        return r["url"]
    return None


def download_mp3(url, temp_path):
    """A function to save the extracted mp3"""
    r = requests.get(url)
    with open(temp_path, "wb") as f:
        f.write(r.content)


def ask_artwork(json, kind, auto="n"):
    # 1. Determine the filename
    if kind == 1:
        print("\033[31m" + "A collection doesn't have an artwork + \033[39m")
        time.sleep(1)
        return
    elif kind == 2:
        name = json["username"]
        if json.get("avatar_url") is None:
            print("Skip → no artwork")
            return
    elif kind in (3, 4, 5):
        name = json["title"]
        if json.get("artwork_url") is None:
            print("Skip → no artwork")
            return
    else:
        print("\033[31m" + "No kind specified" + "\033[39m")
        time.sleep(1)
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
        cover_bytes = save_artwork(json["avatar_url"], f"_{name}", dl)
    else:
        cover_bytes = save_artwork(json["artwork_url"], name, dl)

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

    cover_bytes = session.get(artwork_url).content

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
                    time.sleep(1)
            else:
                print(f"Skip → {cover_filename} already exist")
        except Exception as e:
            print(
                "\033[31m"
                + f"An error occured while downloading cover: {e}"
                + "\033[39m"
            )
            time.sleep(1)
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
        time.sleep(1)


def apply_tags(mp3_path, title, artist, date, cover_bytes):
    """A function to apply tags on the extracted mp3"""
    # 1. Create the ID3 tag
    try:
        audio = ID3(mp3_path)
    except:
        ID3().save(mp3_path)

    # 2. Add tags
    audio = EasyID3(mp3_path)
    if title:
        audio["title"] = title
    if artist:
        audio["artist"] = artist
    if date:
        audio["date"] = date
    audio.save()

    # 3. Add the cover
    if cover_bytes:
        audio = ID3(mp3_path)
        audio.add(
            APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover_bytes)
        )
        audio.save()


def download_soundcloud(url=None, auto="n", json=None, kind=0):
    """A function to extract and download a track"""
    if not json:
        json, kind = get_json(url)
    if kind != 3:
        print("\033[31m" + "Resolve couldn't find a track." + "\033[39m")
        time.sleep(1)
        return

    global outpout
    outpout = ask_outpout() if not outpout else outpout
    if outpout == 0:
        return

    transcoding = pick_transcoding(json)
    mp3_url = get_mp3_url(transcoding["url"], CLIENT_ID)
    global album_artwork
    if json['artwork_url'] in album_artwork:
        cover_bytes = ask_artwork(json, kind, "t")
    else:
        cover_bytes = ask_artwork(json, kind, auto)
        album_artwork.append(json['artwork_url'])

    temp_path = "temp_download.mp3"

    download_mp3(mp3_url, temp_path)

    final_path = f"{outpout}/{re.sub(r'[\\/:*?"<>|]', '', json['title'])}.mp3"

    apply_tags(
        temp_path,
        title=json["title"],
        artist=json["user"]["username"],
        date=json["display_date"].split("-")[0],
        cover_bytes=cover_bytes,
    )
    
    if not os.path.isfile(final_path):
        os.rename(temp_path, final_path)
        print("\033[32m" + f'Téléchargé → {json["title"]}.mp3' + "\033[39m")
    else:
        print(f'Skip → {json["title"]}.mp3 already exist')
    time.sleep(1)


def mode_case1():
    """Option 1 to extract mp3 from a track, playlist or album"""
    url = ask_link()
    json, kind = get_json(url)
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
        download_soundcloud(url=url, auto=auto, json=json, kind=kind)
    elif kind in (4, 5):
        auto = ask("Download everything (mp3, cover) ?")
        dump_json = ask("Ask to download JSON dump ?")
        same_outpout = ask("Same outpout for everything ?")
        if same_outpout == "y":
            global outpout
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
    same_outpout = ask("Same outpout for everything ?")

    if same_outpout == "y":
        global outpout
        outpout = ask_outpout()
        if outpout == 0:
            return

    collection = get_user_collection(link, auto)

    global album_artwork
    print(f"Found {len(collection)} tracks.")
    for t in collection:
        link = t["permalink_url"]

        print(f"\nTrack: {t['title']}")

        if auto == "n":
            dl = ask("Download this track ?")
            if dl == "y":
                download_soundcloud(json=t, kind=3)
        else:
            download_soundcloud(auto=auto, json=t, kind=3)
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
    if os.path.isfile("temp_download.mp3"):
        os.remove("temp_download.mp3")
    while True:
        menu()
