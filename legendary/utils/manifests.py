from legendary.models.manifest import Manifest


def combine_manifests(base_manifest: Manifest, delta_manifest: Manifest):
    added = set()
    # overwrite file elements with the ones from the delta manifest
    for idx, file_elem in enumerate(base_manifest.file_manifest_list.elements):
        try:
            delta_file = delta_manifest.file_manifest_list.get_file_by_path(file_elem.filename)
            base_manifest.file_manifest_list.elements[idx] = delta_file
            added.add(delta_file.filename)
        except ValueError:
            pass

    # add other files that may be missing
    for delta_file in delta_manifest.file_manifest_list.elements:
        if delta_file.filename not in added:
            base_manifest.file_manifest_list.elements.append(delta_file)
    # update count and clear map
    base_manifest.file_manifest_list.count = len(base_manifest.file_manifest_list.elements)
    base_manifest.file_manifest_list._path_map = None

    # ensure guid map exists
    try:
        base_manifest.chunk_data_list.get_chunk_by_guid(0)
    except:
        pass

    # add new chunks from delta manifest to main manifest and again clear maps and update count
    existing_chunk_guids = base_manifest.chunk_data_list._guid_int_map.keys()

    for chunk in delta_manifest.chunk_data_list.elements:
        if chunk.guid_num not in existing_chunk_guids:
            base_manifest.chunk_data_list.elements.append(chunk)

    base_manifest.chunk_data_list.count = len(base_manifest.chunk_data_list.elements)
    base_manifest.chunk_data_list._guid_map = None
    base_manifest.chunk_data_list._guid_int_map = None
    base_manifest.chunk_data_list._path_map = None
