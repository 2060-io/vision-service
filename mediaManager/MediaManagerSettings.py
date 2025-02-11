def generate_mm_settings(rd, d, q):
    # Use 'd' if provided, otherwise fall back to 'rd' if it's not None,
    # or use default 'registry.st.gaiaid.io' if both 'd' and 'rd' are None.
    #data_store_base_url = "https://" + (d if d is not None else ("d." + rd if rd is not None else "d.registry.st.gaiaid.io")) + "/"
    data_store_base_url = (d if d is not None else "d.registry.st.gaiaid.io") + "/"

    # Use 'q' if provided, otherwise fall back to 'rd' if it's not None,
    # or use default 'registry.st.gaiaid.io' if both 'q' and 'rd' are None.
    #vision_service_api_url = "https://" + (q if q is not None else ("q." + rd if rd is not None else "q.registry.st.gaiaid.io")) + "/"
    vision_service_api_url = (q if q is not None else "q.registry.st.gaiaid.io") + "/"
   
    mm_settings = {
        'data_store_base_url': data_store_base_url,
        'create_resource': "c",
        'upload_resource': "u",
        'serve_media_resource': "r",
        'delete_media_resource': "d",
        'vision_service_api_url': vision_service_api_url,
        'link_resource': "link",
        'success_resource': "success",
        'failure_resource': "failure",
        'list_resource': "list"
    }

    return mm_settings