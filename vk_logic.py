# vk_logic.py
import requests
import re
import time
import json


class VkApiError(Exception):
    """Custom exception for VK API errors."""

    def __init__(self, error_data):
        self.code = error_data.get('error_code')
        self.message = error_data.get('error_msg')
        super().__init__(f"VK API Error #{self.code}: {self.message}")


def log(message, buffer, type="info"):
    """Logs messages with a specified type."""
    log_entry = json.dumps({"type": type, "message": message})
    print(log_entry)
    buffer.append(log_entry)


def extract_screen_name(url):
    """Extracts a group's short name from a URL."""
    match = re.search(r'vk\.com/([^/?#&]+)', url.strip())
    if match:
        return match.group(1)
    if not re.search(r'[/\\.]', url.strip()):
        return url.strip()
    raise ValueError(f"Невалідний URL або коротке ім'я: {url}")


def handle_api_response(response):
    """Checks VK API response and raises an error if needed."""
    data = response.json()
    if 'error' in data:
        raise VkApiError(data['error'])
    return data.get('response')


def resolve_group_id(screen_name, token):
    """Gets a group's ID by its short name."""
    url = 'https://api.vk.com/method/utils.resolveScreenName'
    params = {'access_token': token, 'v': '5.131', 'screen_name': screen_name}
    response = requests.get(url, params=params)
    data = handle_api_response(response)
    if data and data.get('type') == 'group':
        return data.get('object_id')
    raise ValueError(f"Не вдалося знайти групу: {screen_name}")


def join_group(group_id, token):
    """Joins a group by its ID."""
    url = 'https://api.vk.com/method/groups.join'
    params = {'access_token': token, 'v': '5.131', 'group_id': group_id}
    response = requests.get(url, params=params)
    return handle_api_response(response)


def post_to_wall(group_id, message, attachments, token, as_group=True):
    """
    Posts a message on a group's wall.
    If as_group is True, it suggests the post.
    If as_group is False, it posts directly from the user's account.
    """
    url = 'https://api.vk.com/method/wall.post'
    params = {
        'access_token': token,
        'v': '5.131',
        'owner_id': f'-{group_id}',
        'message': message,
        'attachments': ','.join(attachments)
    }
    if as_group:
        params['from_group'] = 1

    response = requests.post(url, data=params)
    data = handle_api_response(response)
    post_id = data.get('post_id')
    return f"https://vk.com/wall-{group_id}_{post_id}"


def process_closed_walls(token, message, attachments, group_links, log_buffer, stop_flag):
    """
    Processes posting to 'closed' walls with an automatic join-on-fail mechanism.
    Uses 'suggest post' functionality (as_group=True).
    """
    success_count, failed_count = 0, 0
    successful_links = []
    log(f"🚀 Розпочато процес для 'Закритих стін' ({len(group_links)} груп).", log_buffer, "summary")

    for url in group_links:
        if stop_flag.is_set():
            break

        group_id = None
        try:
            screen_name = extract_screen_name(url)
            log(f"🔍 Обробка: {screen_name}", log_buffer)
            group_id = resolve_group_id(screen_name, token)

            try:
                # First attempt to suggest a post
                post_url = post_to_wall(group_id, message, attachments, token, as_group=True)
                log(f"✅ Запропоновано: {post_url}", log_buffer, "success")
                successful_links.append(post_url)
                success_count += 1
            except VkApiError as e:
                # Check for specific error code 214 (Access to adding post denied)
                if e.code == 214:
                    log(f"⚠️ Помилка доступу ({e.code}). Спроба підписатись на групу...", log_buffer, "info-special")
                    try:
                        join_group(group_id, token)
                        log(f"👍 Успішно підписано. Повторна спроба запропонувати...", log_buffer, "info-special")
                        # Second attempt to suggest a post
                        post_url = post_to_wall(group_id, message, attachments, token, as_group=True)
                        log(f"✅ Запропоновано (2-а спроба): {post_url}", log_buffer, "success")
                        successful_links.append(post_url)
                        success_count += 1
                    except Exception as retry_e:
                        log(f"❌ Не вдалося запропонувати після підписки: {retry_e}", log_buffer, "error")
                        failed_count += 1
                else:
                    # Handle other API errors
                    log(f"❌ Помилка API: {e}", log_buffer, "error")
                    failed_count += 1
        except Exception as general_e:
            log(f"❌ Критична помилка з {url.strip()}: {general_e}", log_buffer, "error")
            failed_count += 1

        time.sleep(2)

    if not stop_flag.is_set():
        log(f"Готово! Успішно запропоновано: {success_count}. Невдало: {failed_count}.", log_buffer, "summary")
        if successful_links:
            log("--- Список успішних пропозицій ---", log_buffer, "summary")
            for link in successful_links:
                log(link, log_buffer, "info")


def process_open_walls(token, message, attachments, group_links, log_buffer, stop_flag):
    """
    Processes posting to 'open' walls directly from the user's account (as_group=False).
    """
    success_count, failed_count = 0, 0
    successful_links = []
    log(f"🚀 Розпочато процес для 'Відкритих стін' ({len(group_links)} груп).", log_buffer, "summary")

    for url in group_links:
        if stop_flag.is_set():
            break

        try:
            screen_name = extract_screen_name(url)
            log(f"🔍 Обробка: {screen_name}", log_buffer)
            group_id = resolve_group_id(screen_name, token)
            # Post directly as user by setting as_group=False
            post_url = post_to_wall(group_id, message, attachments, token, as_group=False)
            log(f"✅ Опубліковано напряму: {post_url}", log_buffer, "success")
            successful_links.append(post_url)
            success_count += 1
        except Exception as e:
            log(f"❌ Помилка з {url.strip()}: {e}", log_buffer, "error")
            failed_count += 1

        time.sleep(2)

    if not stop_flag.is_set():
        log(f"Готово! Успішно опубліковано: {success_count}. Невдало: {failed_count}.", log_buffer, "summary")
        if successful_links:
            log("--- Список успішних публікацій ---", log_buffer, "summary")
            for link in successful_links:
                log(link, log_buffer, "info")
