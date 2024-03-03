import requests
import urllib

stash_headers = {
    "Content-type": "application/json",
}
stash_query = """
findScene(id: "{}") {{
    title
    details
    director
    date
    galleries {{
        folder {{
            path
        }}
        files {{
            path
        }}
    }}
    studio {{
        name
        url
        image_path
        parent_studio {{
            url
        }}
    }}
    tags {{
        name
        parents {{
            name
        }}
    }}
    performers {{
        name
        circumcised
        country
        eye_color
        fake_tits
        gender
        hair_color
        height_cm
        measurements
        piercings
        image_path
        tags {{
            name
        }}
        tattoos
    }}
    paths {{
        screenshot
        preview
    }}
    files {{
        id
        path
        basename
        width
        height
        format
        duration
        video_codec
        audio_codec
        frame_rate
        bit_rate
        size
    }}
}}
"""


def stash_request(body: dict):
    from utils.confighandler import ConfigHandler
    stash_response = requests.post(
        urllib.parse.urljoin(ConfigHandler().get("stash", "url", "http://localhost:9999"), "/graphql"),  # type: ignore
        json=body,
        headers=stash_headers,
    )
    return stash_response


def find_scene(scene_id):
    stash_request_body = {"query": "{" + stash_query.format(scene_id) + "}"}
    return stash_request(stash_request_body)


def find_scenes_by_tag(tag):
    tag_query = """
findTags(tag_filter: {{ name: {{ value: "{}", modifier: EQUALS }} }}) {{
    tags {{
        id
        name
    }}
}}
    """

    response = stash_request({"query": "{" + tag_query.format(tag) + "}"})
    tag_id = response.json()["data"]["findTags"]["tags"][0]["id"]

    scene_query = """
findScenes(scene_filter: {{ tags: {{ value: {}, modifier: INCLUDES }} }}) {{
    count
    scenes {{
        id
        title
    }}
}}
    """
    query = "{" + scene_query.format(tag_id) + "}"
    return stash_request({"query": query}).json()["data"]["findScenes"]
