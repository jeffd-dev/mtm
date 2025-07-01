#!/usr/bin/env python3
import os
from pathlib import Path
import sqlite3
from sys import argv
import shutil

DATABASE_PATH = os.environ.get("MTM_DATABASE", "tag_manager.db")

APP_HELP = """
create/delete tag <tag_name> [<collection_name>]
create/delete collection <collection_name>
show tags/collection
set collection <collection_name> tag <tag_name>
unset collection <collection_name> tag <tag_name>
show collection <collection_name> tags
set file <file_path> tag <tag_name>
unset file <file_path> tag <tag_name>
show tag <tag_name> files [<folder_path>]
show file <file_path> tags 
show folders
search file with <tag_name> [<tag_name>, ...]
search file with-id <tag_name> [<tag_name>, ...]
link folder <folder_path> collection <collection_name> [default-tag <tag_name>]
show linked-folders
search untagged-files <folder_path>
set folder <folder_path> tag <tag_name> [<word_in_name>]

set file <file_path> tag -i  (interactive script mode, <tag_name> is asked after)
set folder <folder_path> tag -i (interactive script mode, <tag_name> is asked after)
set folder <folder_path> files tag -i (interactive mode, <tag_name> is asked for each file)

copy tag <tag_name> files <destination_path>
move tag <tag_name> files <destination_path>
check tag <tag_name> files contains-word <word>
"""


def create_id_from_label(item_name):
	"""Return the lower-case spaceless string of `item_name`"""
	result = item_name.lower()
	return result.replace(" ", "_")


class FilesystemReader:
	def __init__(self, ignored_filetypes=None):
		self.ignored_filetypes = ignored_filetypes

	def get_files(self, path, filetypes=None, ignored=None, search_word=None) -> dict:
		result = {}
		folderpath = Path(path)

		search_words = []
		if search_word is not None:
			search_words = set([search_word, search_word.upper(), search_word.lower(), search_word.title()])

		for item in folderpath.glob("*"):
			if not item.name.startswith("."): # Skip hidden folders
				if len(search_words) > 0:
					for search in search_words:
						if search in item.name:
							result[str(item.absolute())] = (item.name, not item.is_file())
							break
				else:
					result[str(item.absolute())] = (item.name, not item.is_file())

		return result

	def copy_files(self, file_paths:[Path], destination:Path):
		for current_path in file_paths:
			shutil.copy(current_path, destination)

	def move_files(self, file_paths:[Path], destination:Path):
		for current_path in file_paths:
			shutil.move(current_path, destination)


class App:

	def __init__(self):
		self.should_commit = False
		self.data = []
		self.info = ""
		self.fs_reader = FilesystemReader()

		path_to_db = Path(DATABASE_PATH)
		db_exist = path_to_db.exists()
		self.db_connection = sqlite3.connect(path_to_db)
		self.cursor = self.db_connection.cursor() # Connect to db, create file if not exists
		if not db_exist:
			self._app_create_db()

	# COLLECTION: a way to group tags, tag can be created without collection
	def create_new_collection(self, collection_name):
		collection_id = create_id_from_label(collection_name)
		self.cursor.execute("INSERT INTO collection VALUES(?, ?);", (collection_id,collection_name,))
		self.should_commit = True
		self.info = f"New collection {collection_name} created"

	def get_all_collections(self):
		self.cursor.execute("SELECT collection_id, collection_name FROM collection ORDER BY collection_id;")
		self.data = self.cursor.fetchall()

	def delete_collection(self, collection_name):
		self.cursor.execute("DELETE FROM collection WHERE collection_name = ?;", (collection_name,))
		self.should_commit = True
		self.info = f"Collection {collection_name} deleted"

	# COLLECTION-TAG : One tag can have only one collection
	def assign_tag_to_collection(self, tag_name, collection_name):
		self.cursor.execute("UPDATE tag SET collection_id = ? WHERE tag_name = ?;", (create_id_from_label(collection_name), tag_name,))
		self.should_commit = True

	def remove_tag_from_collection(self, tag_name, collection_name):
		self.cursor.execute("UPDATE tag SET collection_id = '' WHERE tag_name = ?;", (tag_name,))
		self.should_commit = True

	def get_all_tags_for_collection(self, collection_name):
		params = (create_id_from_label(collection_name),)
		self.cursor.execute("SELECT tag_id, tag_name FROM tag WHERE collection_id = ?;", params)
		self.data = self.cursor.fetchall()

	# TAG
	def create_new_tag(self, tag_name, collection_name=None):
		tag_id = create_id_from_label(tag_name)
		collection_id = None if not collection_name else create_id_from_label(collection_name)

		self.cursor.execute("INSERT INTO tag VALUES(?, ?, ?);", (tag_id, tag_name, collection_id,))
		self.should_commit = True
		self.info = f"New tag {tag_name} created"

	def get_all_tags(self):
		self.cursor.execute("SELECT tag_id, tag_name, collection_id FROM tag ORDER BY tag_id;")
		self.data = self.cursor.fetchall()

	def delete_tag(self, tag_name):
		tag_id = create_id_from_label(tag_name)
		self.cursor.execute("DELETE FROM tag WHERE tag_id = ?;", (tag_id,) )
		self.should_commit = True
		self.info = f"Tag {tag_name} deleted"

	# TAG-FILE
	def _split_path(self, file_path):
		p = Path(file_path)
		return (str(p.parent), p.name)

	def assign_tag_to_file(self, file_path, tag_name):
		tag_id = create_id_from_label(tag_name)
		folder_path, filename, = self._split_path(file_path)
		params = (folder_path, filename, tag_id,)
		self.cursor.execute("INSERT INTO filetag VALUES(?, ?, ?);", params)
		self.should_commit = True
		self.info = f"File {folder_path} {filename} tagged"

	def assign_tag_to_file_interractive(self, file_path):
		tag_name_input = input("Enter tag for this file:")
		tag_name = tag_name_input.strip(" ")
		self.assign_tag_to_file(file_path, tag_name)

	def remove_tag_from_file(self, file_path, tag_name):
		tag_id = create_id_from_label(tag_name)
		folder_path, filename = self._split_path(file_path)
		params = (tag_id, filename, folder_path,)
		self.cursor.execute("DELETE FROM filetag WHERE tag_id = ? AND filename = ? AND folderpath = ? ;", params)
		self.should_commit = True

	def get_all_files_for_tags(self, tag_names, is_id=False):
		if not is_id:
			params = tuple([create_id_from_label(name) for name in tag_names])
		else:
			params = tuple(tag_names) # in this case this is not names but ids
		tag_count = len(params)
		query_condition = " OR tag_id = ? " * tag_count
		query = f"SELECT folderpath, filename FROM filetag WHERE 1 == 1 {query_condition} GROUP BY folderpath, filename HAVING count() = {tag_count};"
		self.cursor.execute(query, params)
		self.data = self.cursor.fetchall()

	def get_all_files_for_tag(self, tag_name, folder_path_filter=None):
		tag_id = create_id_from_label(tag_name)
		params = (tag_id,)
		query = "SELECT folderpath, filename FROM filetag WHERE tag_id = ?"
		if folder_path_filter:
			query += " AND folderpath = ?"
			params = (tag_id, folder_path_filter.rstrip("/"),)
		query += ";"
		self.cursor.execute(query, params)
		self.data = self.cursor.fetchall()

	def get_all_tags_for_file(self, file_path):
		folder_path, filename, = self._split_path(file_path)
		params = (folder_path, filename,) 
		self.cursor.execute("SELECT tag_id FROM filetag WHERE folderpath = ? AND filename = ?;", params)
		data = self.cursor.fetchall()
		self.data = [tag[0] for tag in data] # Remove tuples and send clear list of tag ids

	def get_folders_with_tagged_content(self):
		self.cursor.execute("SELECT folderpath FROM filetag GROUP BY folderpath;")
		self.data = self.cursor.fetchall()

	# TAG Operations
	def move_tag_files(self, tag_name, destination):
		self.get_all_files_for_tag(tag_name=tag_name)
		filepaths = [Path(p, fn) for p, fn in self.data]
		self.fs_reader.move_files(file_paths=filepaths, destination=destination)

	def copy_tag_files(self, tag_name, destination):
		self.get_all_files_for_tag(tag_name=tag_name)
		filepaths = [Path(p, fn) for p, fn in self.data]
		self.fs_reader.copy_files(file_paths=filepaths, destination=destination)

	def check_tag_files_contains_word(self, tag_name, word):
		self.get_all_files_for_tag(tag_name=tag_name)
		files_without_word = list(filter(lambda a: word not in a[1], self.data))
		self.data = files_without_word

	# FOLDER
	def link_folder(self, folder_path, collection_name, default_tag=None):
		collection_id = create_id_from_label(collection_name)
		default_tag_id = None if default_tag is None else create_id_from_label(default_tag)

		self.cursor.execute("INSERT INTO linkedfolder VALUES(?, ?, ?);", (folder_path, collection_id, default_tag_id,))
		self.should_commit = True
		self.info = f"Folder {folder_path} linked to collection"

	def get_linked_folders(self):
		self.cursor.execute("SELECT folderpath, collection_id, default_tag_id FROM linkedfolder;")
		self.data = self.cursor.fetchall()

	def tag_all_files_from_folder(self, tag_name, folder_path, filetype_filter=None):
		tag_id = create_id_from_label(tag_name)

		docs = self.fs_reader.get_files(path=folder_path, filetypes=None)
		cursor_data = []
		for doc_path, doc_infos in docs.items():
			cursor_data.append((str(folder_path), doc_infos[0], tag_id,))
		self.cursor.executemany("INSERT INTO filetag VALUES(?, ?, ?);", cursor_data)
		self.should_commit = True

	def tag_all_files_from_folder_interractive(self, folder_path):
		tag_name_input = input("Enter tag for the files of this folder: ")
		tag_name = tag_name_input.strip(" ")
		self.tag_all_files_from_folder(tag_name, folder_path)
	
	def tag_all_files_containing_word(self, tag_name, folder_path, word_filter):
		tag_id = create_id_from_label(tag_name)
		
		docs = self.fs_reader.get_files(path=folder_path, search_word=word_filter)
		cursor_data = []
		for doc_path, doc_infos in docs.items():
			cursor_data.append((str(folder_path), doc_infos[0], tag_id,))
		self.cursor.executemany("INSERT INTO filetag VALUES(?, ?, ?)", cursor_data)
		self.should_commit = True

	def get_untagged_file_for_folder(self, folder_path, filetype_filter=None) -> [str]:
		docs_in_fs = self.fs_reader.get_files(path=folder_path, filetypes=filetype_filter)
		path = Path(folder_path)
		tagged_docs = []
		self.cursor.execute("SELECT filename FROM filetag WHERE folderpath = ?", (str(path),))
		for filename in self.cursor.fetchall():
			tagged_docs.append(filename[0])

		untagged_files = []

		for fs_item, fs_infos in docs_in_fs.items():
			if fs_infos[0] not in tagged_docs:
				untagged_files.append(fs_infos[0])

		self.data = untagged_files

	def tag_folder_files_interractive(self, folder_path):
		fs_files = self.fs_reader.get_files(path=folder_path)
		cursor_data = []
		for _, file_infos in fs_files.items():
			print(f"Set tag for {file_infos[0]}:")
			input_tag_name = input(" Tag_name (or SKIP / END): ")
			input_tag = input_tag_name.strip(" ")
			if input_tag.upper() == "SKIP":
				pass
			elif input_tag.upper() == "END":
				break
			else:
				tag_id = create_id_from_label(input_tag)
				cursor_data.append((str(folder_path), file_infos[0], tag_id,))

		self.cursor.executemany("INSERT INTO filetag VALUES(?, ?, ?);", cursor_data)
		self.should_commit = True


	# APP
	def _app_parse_entry(self, parameters):
		"""Read parameters and launch the corresponding action"""
		if len(parameters) == 1:
			if parameters[0].lower() == "help":
				print(APP_HELP)
		elif len(parameters) == 2:
			if parameters[0].lower() == "show":
				if parameters[1].lower() == "collections":
					self.get_all_collections()
				elif parameters[1].lower() == "tags":
					self.get_all_tags()
				elif parameters[1].lower() == "folders":
					self.get_folders_with_tagged_content()
				elif parameters[1].lower() == "linked-folders":
					self.get_linked_folders()
		elif len(parameters) == 3:
			if parameters[0].lower() == "create":
				if parameters[1].lower() == "collection":
					self.create_new_collection(parameters[2])
				elif parameters[1].lower() == "tag":
					self.create_new_tag(parameters[2])
			elif parameters[0].lower() == "delete":
				if parameters[1].lower() == "collection":
					self.delete_collection(parameters[2])
				elif parameters[1].lower() == "tag":
					self.delete_tag(parameters[2])
			elif parameters[0].lower() == "search" and parameters[1].lower() == "untagged-files":
				self.get_untagged_file_for_folder(parameters[2])
		elif len(parameters) == 4:
			if parameters[0].lower() == "create":
				if parameters[1].lower() == "tag":
					self.create_new_tag(parameters[2], parameters[3])
			elif parameters[0].lower() == "show":
				if parameters[1].lower() == "collection":
					if parameters[3].lower() == "tags":
						self.get_all_tags_for_collection(parameters[2])
				elif parameters[1].lower() == "tag":
					if parameters[3].lower() == "files":
						self.get_all_files_for_tag(tag_name=parameters[2])
				elif parameters[1].lower() == "file":
					if parameters[3].lower() == "tags":
						self.get_all_tags_for_file(file_path=parameters[2])
			elif parameters[0].lower() == "search":
				if parameters[1].lower() == "file" and parameters[2].lower() == "with":
					self.get_all_files_for_tags(tag_names=[parameters[3]])
		elif len(parameters) == 5:
			if parameters[0].lower() == "set":
				if parameters[1].lower() == "collection":
					if parameters[3].lower() == "tag":
						self.assign_tag_to_collection(tag_name=parameters[4], collection_name=parameters[2])
				elif parameters[1].lower() == "file":
					if parameters[3].lower() == "tag":
						if parameters[4] == "-i":
							self.assign_tag_to_file_interractive(file_path=parameters[2])
						else:
							self.assign_tag_to_file(file_path=parameters[2], tag_name=parameters[4])
				elif parameters[1].lower() == "folder":
					if parameters[3].lower() == "tag":
						if parameters[4].lower() == "-i":
							self.tag_all_files_from_folder_interractive(folder_path=parameters[2])
						else:
							self.tag_all_files_from_folder(tag_name=parameters[4], folder_path=parameters[2])
			elif parameters[0].lower() == "unset":
				if parameters[1].lower() == "collection":
					if parameters[3].lower() == "tag":
						self.remove_tag_from_collection(tag_name=parameters[4], collection_name=parameters[2])
				elif parameters[1].lower() == "file":
					if parameters[3].lower() == "tag":
						self.remove_tag_from_file(file_path=parameters[2], tag_name=parameters[4])
			elif parameters[0].lower() == "show":
				if parameters[1].lower() == "tag":
					if parameters[3].lower() == "files":
						self.get_all_files_for_tag(tag_name=parameters[2], folder_path_filter=parameters[4])
			elif parameters[0].lower() == "search":
				if parameters[1].lower() == "file" and parameters[2].lower() == "with":
					self.get_all_files_for_tags(tag_names=parameters[3:])
			elif parameters[0].lower() == "link":
				if parameters[1].lower() == "folder" and parameters[3].lower() == "collection":
					self.link_folder(folder_path=parameters[2], collection_name=parameters[4])
			elif parameters[0].lower() == "copy":
				if parameters[1].lower() == "tag" and parameters[3].lower() == "files":
					self.copy_tag_files(tag_name=parameters[2], destination=parameters[4])
			elif parameters[0].lower() == "move":
				if parameters[1].lower() == "tag" and parameters[3].lower() == "files":
					self.move_tag_files(tag_name=parameters[2], destination=parameters[4])
		else: # more than 5 parameters
			if parameters[0].lower() == "link" and parameters[1].lower() == "folder" and parameters[3].lower() == "collection" and parameters[5].lower() == "default-tag":
				self.link_folder(folder_path=parameters[2], collection_name=parameters[4], default_tag=parameters[6])
			elif parameters[0].lower() == "set" and parameters[1].lower() == "folder" and parameters[3].lower() == "tag":
				self.tag_all_files_containing_word(tag_name=parameters[4], folder_path=parameters[2], word_filter=parameters[5])
			elif parameters[0].lower() == "set" and parameters[1].lower() == "folder" and parameters[3].lower() == "files" and parameters[4].lower() == "tag":
				if parameters[5].lower() == "-i":
					self.tag_folder_files_interractive(folder_path=parameters[2])
			elif parameters[0].lower() == "check" and parameters[1].lower() == "tag" and parameters[3].lower() == "files" and parameters[4].lower() == "contains-word":
				self.check_tag_files_contains_word(tag_name=parameters[2], word=parameters[5])
			elif parameters[0].lower() == "search":
				if parameters[1].lower() == "file" and parameters[2].lower() == "with":
					self.get_all_files_for_tags(tag_names=parameters[3:])
				elif parameters[1].lower() == "file" and parameters[2].lower() == "with-id":
					self.get_all_files_for_tags(tag_names=parameters[3:], is_id=True)

	def _app_create_db(self):
		self.cursor.execute("CREATE TABLE collection(collection_id, collection_name);")
		self.cursor.execute("CREATE TABLE tag(tag_id, tag_name, collection_id);")
		self.cursor.execute("CREATE TABLE filetag(folderpath, filename, tag_id);")
		self.cursor.execute("CREATE TABLE linkedfolder(folderpath, collection_id, default_tag_id);")
		self.db_connection.commit()

	def execute(self, args, print_result=True):
		"""Can be used to directly receive command by GUI"""
		if len(args) == 0:
			print("Use `help`to list fonctions")
			return
		
		self._app_parse_entry(args)
		if self.should_commit:
			self.db_connection.commit()
		if print_result:
			if len(self.info):
				print(self.info)
			if len(self.data):
				print(self.data)
		else:
			return list(self.data)

	def quit(self):
		try:
			self.db_connection.close()
		except Exception as e:
			print(f"Fail to close DB: {e}")

	def main(self, cli_args=None):
		"""Run application in CLI mode: read one command and close DB"""
		print("Minimalist Tag Manager v0.1a")
		try:
			self.execute(cli_args)
		except Exception as e:
			print(e)
		finally:
			self.quit()
		exit()


if __name__ == "__main__":
	App().main(argv[1:])