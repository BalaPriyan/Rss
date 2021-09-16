import telegram.error
import time
import logging
import fasteners
from typing import List, Union, Optional, Tuple

from medium import Medium
import env


class Message:
    _lock = fasteners.ReaderWriterLock()

    def __init__(self,
                 text: Optional[str] = None,
                 media: Optional[Union[List[Medium], Tuple[Medium], Medium]] = None,
                 parse_mode: Optional[str] = 'HTML'):
        self.text = text
        self.media = media
        self.parse_mode = parse_mode
        self.retries = 0

    def send(self, chat_id: Union[str, int]):
        if self.no_retry and self.retries >= 1:
            logging.warning('Message dropped: this message was configured not to retry.')
            return
        elif self.retries >= 1:
            return
        elif self.retries >= 3:  # retried twice, tried 3 times in total
            logging.warning('Message dropped: retried for too many times.')
            raise OverflowError

        try:
            self._send(chat_id)
        except telegram.error.RetryAfter as e:  # exceed flood control
            logging.warning(e.message)
            self.retries += 1
            if not Message._lock.owner == Message._lock.WRITER:  # if not already blocking
                with Message._lock.write_lock():  # block any other sending tries
                    time.sleep(e.retry_after + 1)
            self.send(chat_id)
        except telegram.error.BadRequest as e:
            if self.no_retry:
                logging.warning('Something went wrong while sending a message. Please check:', exc_info=e)
                return
            raise e  # let post.py to deal with it
        except telegram.error.NetworkError as e:
            logging.warning(f'Network error({e.message}). Retrying...')
            self.retries += 1
            time.sleep(1)
            self.send(chat_id)

    def _send(self, chat_id: Union[str, int]):
        pass


class TextMsg(Message):
    @fasteners.lock.read_locked
    def _send(self, chat_id: Union[str, int]):
        env.bot.send_message(chat_id, self.text, parse_mode=self.parse_mode, disable_web_page_preview=True)


class PhotoMsg(Message):
    @fasteners.lock.read_locked
    def _send(self, chat_id: Union[str, int]):
        env.bot.send_photo(chat_id, self.media.get_url(), caption=self.text, parse_mode=self.parse_mode)


class VideoMsg(Message):
    @fasteners.lock.read_locked
    def _send(self, chat_id: Union[str, int]):
        env.bot.send_video(chat_id, self.media.get_url(), caption=self.text, parse_mode=self.parse_mode)


class AnimationMsg(Message):
    @fasteners.lock.read_locked
    def _send(self, chat_id: Union[str, int]):
        env.bot.send_animation(chat_id, self.media.get_url(), caption=self.text, parse_mode=self.parse_mode)


class MediaGroupMsg(Message):
    @fasteners.lock.read_locked
    def _send(self, chat_id: Union[str, int]):
        media_list = list(map(lambda m: m.telegramize(), self.media))
        media_list[0].caption = self.text
        media_list[0].parse_mode = self.parse_mode
        env.bot.send_media_group(chat_id, media_list)
