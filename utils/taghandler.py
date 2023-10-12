"""This module provides an object for storing and processing stash scene tags
for uploading to empornium."""

import configupdater
import re
import logging

class TagHandler:
    logger: logging.Logger
    conf: configupdater.ConfigUpdater
    TAGS_MAP: dict[str,str] = {}
    TAG_LISTS: dict[str, list[str]] = {}
    tag_sets: dict[str,set] = {}

    # Dict of autogenerated tag suggestions
    tag_suggestions: dict[str,str] = {}

    # Set of tags to apply to the current scene
    tags: set[str] = set()
    
    def __init__(self, conf: configupdater.ConfigUpdater) -> None:
        """Initialize a TagHandler object from a config object."""
        self.logger = logging.getLogger(__name__)
        assert conf._filename is not None
        self.conf = conf
        self.TAGS_MAP = conf["empornium.tags"].to_dict()
        for key in conf["empornium"]:
            self.TAG_LISTS[key] = list(map(lambda x: x.strip(), conf["empornium"][key].value.split(","))) # type: ignore
            self.TAG_LISTS[key].sort()
            conf["empornium"].set(key, self.TAG_LISTS[key])
            self.tag_sets[key] = set()
        conf.update_file()
        assert "sex_acts" in self.TAG_LISTS

    def sortTagList(self, tagset: str) -> list[str]:
        """Return a sorted list for a given
        tag set name, or an empty list if
        the requested set does not exist."""
        if tagset in self.tag_sets:
            tmp = list(self.tag_sets[tagset])
            tmp.sort()
            return tmp
        return []
    
    def sortTagLists(self) -> dict[str,list[str]]:
        """Returns a dictionary where the keys are
        the names of custom lists and the associated
        values are the sorted lists of tags from the
        current scene."""
        return {key: self.sortTagList(key) for key in self.keys()}

    def processTag(self, tag: str) -> None:
        """Check for the appropriate EMP tag
        mapping for a provided tag and add it to
        the working lists, or generate a suggested
        mapping."""
        if "ignored_tags" in self.TAG_LISTS and tag in self.TAG_LISTS["ignored_tags"]:
            return None
        if tag.lower() in self.TAGS_MAP:
            self.tags.add(self.TAGS_MAP[tag.lower()])
        else:
            self.tag_suggestions[tag.lower()] = self.empify(tag)
        for key in self.TAG_LISTS:
            if tag in self.TAG_LISTS[key]:
                self.tag_sets[key].add(tag)

    def empify(self, tag: str) -> str:
        """Return an EMP-compatible tag for a given input 
        tag. This function replaces all whitespace with a 
        '.' and strips out all other characters that are 
        not alphanumeric before finally converting the full 
        string to lowercase."""
        newtag = re.sub(r"[^\w\s]", "", tag).lower()
        newtag = re.sub(r"\s+", ".", tag)
        self.logger.debug(f"Reformatted tag '{tag}' to '{newtag}'")
        return newtag

    def add(self, tag: str) -> str:
        """Convert a tag to en EMP-compatible
        version and add it to the main list, 
        skipping the check for custom lists.
        Returns the EMP-compatible tag."""
        tag = self.empify(tag)
        self.tags.add(tag)
        return tag
    
    def update_file(self) -> bool:
        updated = False
        try:
            self.conf.update_file()
            updated = True
            self.logger.debug("Saved configuration")
        except:
            pass
        return updated
    
    def acceptSuggestions(self, tags: dict[str,str]) -> bool:
        """Adds the provided tag mappings to the working config
        and attempts to update the config file. Returns True if
        update is successful and False otherwise."""
        self.logger.info("Saving tag mappings")
        self.logger.debug(f"Tags: {tags}")
        for tag in tags:
            self.conf["empornium.tags"].set(tag, tags[tag])
            tag = tag.lower()
            self.TAGS_MAP[tag] = tags[tag]
            if tag in self.tag_suggestions:
                self.tag_suggestions.pop(tag)
        return self.update_file()

    def rejectSuggestions(self, tags: list[str]) -> bool:
        """Adds all supplied tags to the list of ignored
        tags and attempts to update the config file. Returns 
        True if update is successful and False otherwise."""
        self.logger.debug(f"Ignoring tags: {tags}")
        if "ignored_tags" not in self.TAG_LISTS:
            self.TAG_LISTS["ignored_tags"] = []
        for tag in tags:
            self.TAG_LISTS["ignored_tags"].append(tag)
            if tag in self.tag_suggestions:
                self.tag_suggestions.pop(tag)
        self.TAG_LISTS["ignored_tags"].sort()
        self.conf.set("empornium", "ignored_tags", ", ".join(self.TAG_LISTS["ignored_tags"]))
        return self.update_file()

    def keys(self) -> list[str]:
        return [key for key in self.TAG_LISTS]

    def clear(self) -> None:
        """Reset the working tag sets without
        clearing the mapping or custom list
        definitions."""
        for tagset in self.tag_sets:
            self.tag_sets[tagset].clear()
        self.tag_suggestions.clear()
        self.tags.clear()