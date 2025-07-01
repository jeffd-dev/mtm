import tkinter as tk
from enum import Enum
from tkinter import simpledialog, Menu, messagebox, filedialog
import ttkbootstrap as ttk
from ttkbootstrap import constants as ttkbconsts
from functools import partial
import subprocess
from pathlib import Path

from mtm import App, create_id_from_label


MAX_ITEMS_BY_ROW = 5
MAX_FILENAME_LEN = 36
DEFAULT_VIEW = "VIEW_COLUMN"


class RightMenuType(Enum):
    UNSET = "Empty"
    FILE = "File"
    FOLDER = "Folder"
    TAG = "TAG"


class GraphicalApp:
    def __init__(self):
        self.selector_frame = None
        self.filesystem_frame = None
        self.fs_context_menu = None
        self.fs_rigth_menu_frame = None
        self.fs_right_menu_type = RightMenuType.UNSET

        # GUI Item selected
        self.selected_collection:tuple = None 
        self.selected_tags = []
        self.selected_filesystem_folder_path:str = None
        self.selected_filesystem_file_path:str = None
        
        self.core_app = App()
        self.fs_reader = self.core_app.fs_reader

        # Cache
        self.my_collections = {}
        self.my_tags = {} # Used to display anmes or when the collection is unknow (show file tags)
        self.tags_by_collection = {}
        data_collections = self._app_execute(command_args=["show", "collections"])
        for d in data_collections:
            self.my_collections[d[0]] = d[1]
            # Init tags, creating empty dicts for each collection 
            self.tags_by_collection[d[0]] = {}

        data_tags = self._app_execute(command_args=["show", "tags"])
        for tid, tname, tcollection in data_tags:
            try:
                self.my_tags[tid] = tname
                self.tags_by_collection[tcollection][tid] = tname
            except KeyError:
                pass # Skip tag for undefined collection

        data_folders = self._app_execute(command_args=["show", "folders"])
        self.my_tagged_folders = {d[0]: (Path(d[0]).name, True) for d in data_folders}

        self.my_linked_folders = {}
        data_link_folders = self._app_execute(command_args=["show", "linked-folders"])
        for linked_folder in data_link_folders:
            self.my_linked_folders[linked_folder[0]] = (linked_folder[1], linked_folder[2]) # Collection_id, default_tag

    def _get_tags(self):
        if self.selected_collection is not None:
            return self.tags_by_collection[self.selected_collection[0]]
        return {}

    def _app_execute(self, command_args:[]):
        try:
            #print("DEBUG CMD: {}".format(" ".join(command_args)))
            return self.core_app.execute(command_args, print_result=False)
        except Exception as e:
            messagebox.showerror(message=str(e))
            return

    def launch_action(self, action_name, *args):
        # MAIN MENU ACTIONS
        if action_name == "HOME":
            self.selected_tags = []
            self._load_collections_frame()
            self._load_filesystem_frame()
        elif action_name == "OPEN_PATH":
            dirname = filedialog.askdirectory()
            if dirname is not None and len(dirname) > 1:
                self.selected_filesystem_folder_path = dirname
                self.action_open_folder()
                self._load_filesystem_menu(menu_type=RightMenuType.FOLDER)
        elif action_name == "OPEN_TAG_ACTION_MENU":
            self._load_filesystem_menu(menu_type=RightMenuType.TAG)
        elif action_name == "CREATE_COLLECTION":
            self.action_create_collection()
        elif action_name == "CREATE_TAG":
            self.action_create_tag()
        # MENU for FOLDER
        elif action_name == "OPEN_FOLDER":
            self.action_open_folder()
        elif action_name == "LINK_FOLDER":
            self.action_link_folder()
        elif action_name == "TAG_ALL_FILES":
            self.action_tag_all_files()
        elif action_name == "SEARCH_UNTAGGED":
            self.selected_tags = []
            untagged_files = self._app_execute(command_args=["search", "untagged-files", self.selected_filesystem_folder_path])
            untagged_dict = {f"{self.selected_filesystem_folder_path}/{filename}": (filename, False) for filename in untagged_files}
            self._load_filesystem_frame(data=untagged_dict)
        # MENU for FILES
        elif action_name == "OPEN_FILE":
            subprocess.Popen(["open", self.selected_filesystem_file_path])
        elif action_name == "OPEN_EXTERNAL_GUI":
            subprocess.Popen(["open", self.selected_filesystem_folder_path])
        elif action_name == "OPEN_EXTERNAL_CLI":
            file_path = Path(self.selected_filesystem_file_path)
            subprocess.Popen(["terminator", f"--working-directory={file_path.parent}"])
        elif action_name == "TAG_FILE":
            self.action_tag_file()
        elif action_name == "REMOVE_TAGS":
            self.action_remove_tag_file()
        elif action_name == "SEE_TAGS":
            tag_ids = self._app_execute(command_args=["show", "file", self.selected_filesystem_file_path, "tags"])
            tag_names = [self.my_tags.get(tid) for tid in tag_ids if tid in self.my_tags]
            if len(tag_names):
                messagebox.showinfo(message="Tags: {}".format(", ".join(tag_names)))
            else:
                messagebox.showinfo(message="No tags: found")
        # MENU for TAGS
        elif action_name == "MOVE_FILES":
            destination_directory = filedialog.askdirectory()
            if destination_directory is not None and len(destination_directory) > 1:
                self._app_execute(command_args=["move", "tag", self.selected_tags[0], "files", destination_directory])
        elif action_name == "COPY_FILES":
            destination_directory = filedialog.askdirectory()
            if destination_directory is not None and len(destination_directory) > 1:
                self._app_execute(command_args=["copy", "tag", self.selected_tags[0], "files", destination_directory])
        elif action_name == "CHECK_NAME_CONTAINS":
            mandatory_word = simpledialog.askstring("Check filename contains word", "Word:")
            if mandatory_word is not None:
                file_without_word = self._app_execute(command_args=["check", "tag", self.selected_tags[0], "files", "contains-word", mandatory_word])
                fs_items = {f"{filepath}/{filename}": (filename, False) for filepath, filename in file_without_word}
                self._load_filesystem_frame(data=fs_items)

    def action_create_collection(self):
        my_collection_name = simpledialog.askstring("Create new collection", "Collection name:")
        if my_collection_name is not None:
            self._app_execute(command_args=["create", "collection", my_collection_name])

            # For performance issue we add manually (avoid to re-read db-table)
            new_collection_id = create_id_from_label(my_collection_name)
            self.my_collections[new_collection_id] = my_collection_name
            self.tags_by_collection[new_collection_id] = {}
            self._load_collections_frame()

    def action_create_tag(self):
        if not self.selected_collection:
            messagebox.showerror(message="Can not create tag outside collection")
            return
        
        title = "Create new tag for {}".format(self.selected_collection[1])
        my_tag_name = simpledialog.askstring(title, "Tag name:")
        if my_tag_name is not None:
            self._app_execute(command_args=["create", "tag", my_tag_name, self.selected_collection[1]]) # We add collection name, not id
            tag_id = create_id_from_label(my_tag_name)
            self.tags_by_collection[self.selected_collection[0]][tag_id] = my_tag_name
            self.my_tags[tag_id] = my_tag_name
            self._load_tags_frame()

    def action_tag_all_files(self):
        tags_to_use = self.selected_tags
        if len(tags_to_use) < 1:
            tag_names = simpledialog.askstring("Tag files", "Tag names (separator `;`)")
            if tag_names is not None and len(tag_names.strip()) > 1:
                for tag_name in [n.strip() for n in tag_names.split(";")]:
                    if tag_name not in self._get_tags():
                        messagebox.showinfo(message=f"Tag {tag_name} not found")
                        return
                    tags_to_use.append(tag_name)
            
        message = "Tag all files in this directory with the {} tags ?".format(len(tags_to_use))
        result = messagebox.askyesno(message=message, title="Tag all files")
        if result:
            for tag_to_use in tags_to_use:
                self._app_execute(command_args=["set", "folder", self.selected_filesystem_folder_path, "tag", tag_to_use])
    
    def action_tag_file(self, tag_name):
        self._app_execute(command_args=["set", "file", self.selected_filesystem_file_path, "tag", tag_name])

    def action_remove_tag_file(self):
        tag_ids = self._app_execute(command_args=["show", "file", self.selected_filesystem_file_path, "tags"])
        current_tags = [self.my_tags.get(tid) for tid in tag_ids if tid in self.my_tags]
        
        tags_to_remove = []
        ctags = ",".join(current_tags)
        tag_names = simpledialog.askstring("Remove tags", f"Current tags: {ctags} - Remove: (separator `;`)")
        if tag_names is not None and len(tag_names.strip()) > 1:
            for tag_name in [n.strip() for n in tag_names.split(";")]:
                if tag_name in current_tags:
                    tags_to_remove.append(tag_name)
        for tag in tags_to_remove:
            self._app_execute(command_args=["unset", "file", self.selected_filesystem_file_path, "tag", tag_name])

    def _action_select_collection(self, selected_collection_id):
        is_first_selection = self.selected_collection is None
        self.selected_collection = (selected_collection_id, self.my_collections[selected_collection_id])
        self._load_tags_frame(collection_id=selected_collection_id)
        if is_first_selection and self.fs_right_menu_type == RightMenuType.FILE:
            # Reload the Right Menu to display the TAG button
            self.fs_right_menu_type = RightMenuType.UNSET
            self._load_filesystem_menu(menu_type=RightMenuType.FILE)
            
    def _action_select_folder(self, folder_path):
        self.selected_filesystem_folder_path = folder_path
        self._load_filesystem_menu(menu_type=RightMenuType.FOLDER)

    def action_open_folder(self):
        self.selected_tags = []
        self._reload_selector_frame()
        folder_content = self.fs_reader.get_files(self.selected_filesystem_folder_path)
        self._load_filesystem_frame(data=folder_content)

    def action_link_folder(self):
        if not self.selected_collection:
            messagebox.showerror(message="Select collection before")
            return

        if len(self.selected_tags) == 1:
            default_tag_id = self.selected_tags[0]
            default_tag = self._get_tags().get(default_tag_id)
            default_tag_suffix = f" with {default_tag} as default-tag"
        else:
            default_tag = None
            default_tag_suffix = ""

        result = messagebox.askyesno(message=f"Link folder to collection {self.selected_collection[1]}{default_tag_suffix}", title="Link folder")
        if result:
            args = ["link", "folder", self.selected_filesystem_folder_path, "collection", self.selected_collection[1]]
            if default_tag:
                args.append("default-tag", default_tag)

            self._app_execute(command_args=args) # We add collection name, not id

    def _action_select_file(self, file_path):
        self.selected_filesystem_file_path = file_path
        self._load_filesystem_menu(menu_type=RightMenuType.FILE)

    def _action_select_tag(self, selected_tag_id):
        if selected_tag_id in self.selected_tags:
            self.selected_tags.remove(selected_tag_id)
        else:
            self.selected_tags.append(selected_tag_id)

        self._load_tags_frame()
        self._load_filesystem_frame()

    def _reload_selector_frame(self):
        if len(self.selected_tags) > 0:
            # If some tags are selected
            self._load_tags_frame(collection_id=self.selected_collection[0])
        elif self.selected_collection is not None:
            self._load_tags_frame(collection_id=self.selected_collection[0])
        else:
            self._load_collections_frame()

    def _load_collections_frame(self):
        # Delete existing elements 
        for child in self.selector_frame.winfo_children(): 
            child.destroy()

        # Create new collection button
        ttk.Button(self.selector_frame, bootstyle="outline", text="+", command=lambda:self.launch_action("CREATE_COLLECTION")).grid(column=1, row=1, sticky=ttkbconsts.W)
        
        for column_position, collection_id in enumerate(self.my_collections.keys(), 2):
            ttk.Button(self.selector_frame, bootstyle="outline", text=self.my_collections[collection_id], command=partial(self._action_select_collection,collection_id)).grid(column=column_position, row=1, sticky=ttkbconsts.W, padx=3, pady=3)

    def _load_tags_frame(self, collection_id=None):
        # Delete existing elements 
        for child in self.selector_frame.winfo_children(): 
            child.destroy()

        # Create current collection Button (disabled)
        ttk.Button(self.selector_frame, bootstyle="", text=self.selected_collection[1]).grid(column=1, row=1, sticky=ttkbconsts.W, padx=3, pady=3)

        # Create new tag button  
        ttk.Button(self.selector_frame, bootstyle="outline info", text="+", command=partial(self.launch_action, "CREATE_TAG")).grid(column=2, row=1, sticky=ttkbconsts.W, padx=3, pady=3)
        
        for column_position, tag_id in enumerate(self._get_tags().keys(), 3):
            style = "solid info" if tag_id in self.selected_tags else "outline info"

            ttk.Button(self.selector_frame, bootstyle=style, text=self._get_tags()[tag_id], command=partial(self._action_select_tag, tag_id)).grid(column=column_position, row=1, sticky=ttkbconsts.W, padx=3, pady=3)

    def _load_filesystem_frame(self, data:dict=None):

        for child in self.filesystem_frame.winfo_children(): 
            child.destroy()

        if data is not None:
            pass
        elif len(self.selected_tags) == 0:
            if data is None:
                # Default view: display tagged folders
                data = self.my_tagged_folders
        else:
            if len(self.selected_tags) == 1:
                args =["show", "tag", self.selected_tags[0], "files"]
            else:
                args = ["search", "file", "with"] + self.selected_tags
            
            tagged_files = self._app_execute(command_args=args) # format list:  [(path, nom), ...]
            data = {f"{filepath}/{filename}": (filename, False) for filepath, filename in tagged_files}

        row_position, col_position = (1, 1)
        for item_pos_id, item_path in enumerate(data.keys(), 1):
            action = self._action_select_folder if data[item_path][1] else self._action_select_file
            style = "solid secondary" if data[item_path][1] else "solid light"
            b = ttk.Button(self.filesystem_frame, bootstyle=style, text=data[item_path][0][:MAX_FILENAME_LEN], command=partial(action, item_path))
            b.grid(column=col_position, row=row_position, sticky=ttkbconsts.W, padx=3, pady=3)
            b.bind("<Button-3>", self.display_filesystem_context_menu)

            if item_pos_id % (MAX_ITEMS_BY_ROW) == 0:
                row_position += 1
                col_position = 1
            else:
                col_position += 1

    def _load_filesystem_menu(self, menu_type:RightMenuType):
        if (self.fs_right_menu_type.value != menu_type.value):
            # Delete existing elements 
            for child in self.fs_rigth_menu_frame.winfo_children(): 
                child.destroy()

            start_button_position = 1

            if menu_type == RightMenuType.FOLDER:
                actions = {
                    "OPEN_FOLDER": "Open",
                    "LINK_FOLDER": "Link to collection",
                    "TAG_ALL_FILES": "Tag all files",
                    "SEARCH_UNTAGGED": "Search untagged files",
                }
            elif menu_type == RightMenuType.FILE:
                actions = {
                    "OPEN_FILE": "Open",
                    "OPEN_EXTERNAL_GUI": "Open (nautilus)",
                    "OPEN_EXTERNAL_CLI": "Open (terminal)",
                    "SEE_TAGS": "See tags",
                    "REMOVE_TAGS": "Remove tags",
                }

                if self.selected_collection is not None:
                    menu_button = ttk.Menubutton(self.fs_rigth_menu_frame, text="TAG")
                    menu_button.grid(column=1, row=1, sticky=ttkbconsts.W, padx=3, pady=3)
                    start_button_position = 2
                    tag_menu = Menu(menu_button, tearoff = 0)

                    for tag_id, tag_name in self._get_tags().items():
                        tag_menu.add_command(label=tag_name, command=partial(self.action_tag_file, tag_name))
                    
                    menu_button["menu"] = tag_menu

            else: # RightMenuType.Tag
                actions = {
                    "MOVE_FILES": "Move files",
                    "COPY_FILES": "Copy files",
                    "CHECK_NAME_CONTAINS": "Check filename contain words",
                }
                ttk.Label(self.fs_rigth_menu_frame, text="For files with selected tags").grid(column=1, row=1, sticky=ttkbconsts.W, padx=3, pady=3)
                start_button_position = 2

            self.fs_right_menu_type = menu_type
            
            for row_position, action_key in enumerate(actions, start_button_position):
                ttk.Button(self.fs_rigth_menu_frame, bootstyle=(ttkbconsts.SECONDARY, "outline"), text=actions[action_key], command=partial(self.launch_action, action_key)).grid(column=1, row=row_position, sticky=ttkbconsts.W, padx=3, pady=3)

    def display_filesystem_context_menu(self, event):
        try:
            self.fs_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.fs_context_menu.grab_release()

    def run(self):
        root = ttk.Window(themename="united")

        def _windows_closed():
            self.core_app.quit()
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", _windows_closed)
        root.title("Minimalist Tag Manager")
        appdisplay =  ttk.Frame(root, padding="5 5 5 5")
        appdisplay.grid(column=2, row=0, sticky=(ttkbconsts.N, ttkbconsts.W, ttkbconsts.E, ttkbconsts.S))
        root.columnconfigure(0, weight=10)
        root.rowconfigure(0, weight=1)

        # Menu
        actions = {
            "HOME": "Accueil",
            "OPEN_PATH": "Open path",
            "OPEN_TAG_ACTION_MENU": "Tag opération",
        }

        menu_frame =  ttk.Frame(appdisplay, padding="5 5 5 5")
        menu_frame.grid(column=1, row=0, rowspan=len(actions),  sticky=(ttkbconsts.W))

        row_position = 1
        for action_key, action_label in actions.items():
            ttk.Button(menu_frame, bootstyle=(ttkbconsts.SECONDARY, "outline"), text=action_label, command=partial(self.launch_action,action_key)).grid(column=1, row=row_position, sticky=ttkbconsts.W, padx=3, pady=3)
            row_position += 1

        ttk.Separator(appdisplay, orient=tk.VERTICAL).grid(column=2, rowspan=10, row=0, sticky=(ttkbconsts.N, ttkbconsts.W, ttkbconsts.E, ttkbconsts.S))

        # Collections / Tags
        self.selector_frame =  ttk.Frame(appdisplay, padding="5 5 5 5")
        self.selector_frame.grid(column=3, row=0, sticky=(ttkbconsts.N, ttkbconsts.W, ttkbconsts.E, ttkbconsts.S))
        self._load_collections_frame()

        ttk.Separator(appdisplay, orient=tk.HORIZONTAL).grid(column=3, row=1, sticky=(ttkbconsts.N, ttkbconsts.W, ttkbconsts.E, ttkbconsts.S))

        self.filesystem_frame =  ttk.Frame(appdisplay, padding="5 5 5 5")
        self.filesystem_frame.grid(column=3, row=2, sticky=(ttkbconsts.N, ttkbconsts.W, ttkbconsts.E, ttkbconsts.S))
        self._load_filesystem_frame()

        ttk.Separator(appdisplay, orient=tk.VERTICAL).grid(column=4, row=0, rowspan=10, sticky=(ttkbconsts.N, ttkbconsts.W, ttkbconsts.E, ttkbconsts.S))       

        # RIGHT Menu (file, folder and tag operations)
        self.fs_rigth_menu_frame = ttk.Frame(appdisplay, padding="5 5 5 5")
        self.fs_rigth_menu_frame.grid(column=5, row=1, sticky=(ttkbconsts.N, ttkbconsts.W, ttkbconsts.E, ttkbconsts.S))
        self._load_filesystem_menu(menu_type=RightMenuType.FOLDER)
        

        # Contextual click rigth menu
        self.fs_context_menu = Menu(root, tearoff=0)
        self.fs_context_menu.add_command(label="Open", command=None)
        self.fs_context_menu.add_command(label="See in Nautilus")
        self.fs_context_menu.add_command(label="Tag")
        self.fs_context_menu.add_separator()
        self.fs_context_menu.add_command(label="Move")
        self.fs_context_menu.add_command(label="Rename")
        
        root.mainloop()


if __name__ == "__main__":
    app = GraphicalApp()
    app.run()