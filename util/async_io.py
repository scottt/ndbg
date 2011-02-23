# Copyright 2011 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import asyncore
from asynchat import async_chat
import socket

from util import *

_iothread = None

class AsyncIO(object):
  def __init__(self, h):
    self._read = Event()
    self._close = Event()
    self._opened = False
    self._open(h)

  def _set_dispatcher(self, dispatcher):
    self._dispatcher = dispatcher

  def _open(self, h):
    if not (isinstance(h, socket.socket) or isinstance(h, file)):
      raise Exception("AsyncIO for supported only for sockets and files")
    _IOThread.open(self, h)

  @property
  def read(self):
    return self._read

  def write(self, data, on_write_cb = None):
    self._dispatcher._queue_write(data, on_write_cb)

  @property
  def closed(self):
    return self._close

  @property
  def is_closed():
    return self._dispatcher == None

  def _on_close(self):
    self._dispatcher = None
    self.closed.fire()


class _AsyncIODispatcher(asyncore.dispatcher):
  def __init__(self, handle, socket):
    asyncore.dispatcher.__init__(self, sock=socket)
    self._handle = handle
    assert handle
    self._pending_sends = []
    self._closed = False

  def handle_read(self, *args):
#    print "recv: ", args
    if self._closed:
      return
    buffer = self.recv(8192)
    MessageLoop.add_message(lambda: self._handle._read.fire(buffer))

  def _queue_write(self,data,cb=None):
    cmd = DynObject()
    cmd.data = data
    if cb:
      cmd.cb = cb
    else:
      cmd.cb = lambda: None
    self._pending_sends.append(cmd)

  def handle_write(self):
    if len(self._pending_sends):
#      print "sending queue has an %i byte send" % len(self._pending_sends[0].data)
      sent = self.send(self._pending_sends[0].data)
#      print "%i sent" % sent
      self._pending_sends[0].data = self._pending_sends[0].data[sent:]
      if len(self._pending_sends[0].data) == 0:
        MessageLoop.add_message(self._pending_sends[0].cb)
        del self._pending_sends[0]

  def handle_close(self):
    self._closed = True
    del self._pending_sends[:]
    MessageLoop.add_message(self._handle._on_close)


class _IOThread(WellBehavedThread):
  @staticmethod
  def get():
    global _iothread
    if not _iothread:
      _iothread = _IOThread()
      _iothread.start()
    return _iothread

  def __init__(self):
    WellBehavedThread.__init__(self, "IOThread", self._idle)

  @staticmethod
  def open(h,f):
    done = BoxedObject()
    def create_dispatcher():
      if isinstance(f,socket.socket):
        dispatcher = _AsyncIODispatcher(h, f)
      done.set(dispatcher)
    _IOThread.get().add_message(create_dispatcher)
    MessageLoop.run_until(lambda: done.get())
    h._set_dispatcher(done.get())
    return

  def _idle(self):
#    log2("poll")
    try:
      asyncore.poll(timeout=0.1)
    except:
      pass
