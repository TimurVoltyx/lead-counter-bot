Starting Container

2025-08-09 04:58:14,766 | INFO | root | Running webhook at 0.0.0.0:8080 path=/hook-1111 url=https://lead-counter-bot-production.up.railway.app/hook-1111

2025-08-09 04:58:15,220 | INFO | httpx | HTTP Request: POST https://api.telegram.org/bot8190019941:AAHkTZIJ1eE8nq2oQf0M0swTb6co73MRQMo/getMe "HTTP/1.1 200 OK"

2025-08-09 04:58:15,369 | INFO | httpx | HTTP Request: POST https://api.telegram.org/bot8190019941:AAHkTZIJ1eE8nq2oQf0M0swTb6co73MRQMo/setWebhook "HTTP/1.1 400 Bad Request"

2025-08-09 04:58:15,370 | ERROR | telegram.ext.Updater | Error while bootstrap set webhook: Bad webhook: an https url must be provided for webhook

2025-08-09 04:58:15,370 | ERROR | telegram.ext.Updater | Failed bootstrap phase after 0 retries (Bad webhook: an https url must be provided for webhook)

Traceback (most recent call last):

  File "/app/bot.py", line 156, in <module>

    main()

  File "/app/bot.py", line 147, in main

    app.run_webhook(

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_application.py", line 1032, in run_webhook

    return self.__run(

           ^^^^^^^^^^^

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_application.py", line 1085, in __run

    loop.run_until_complete(updater_coroutine)  # one of updater.start_webhook/polling

    ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

  File "/root/.nix-profile/lib/python3.12/asyncio/base_events.py", line 687, in run_until_complete

    return future.result()

           ^^^^^^^^^^^^^^^

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_updater.py", line 628, in start_webhook

    raise exc

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_updater.py", line 606, in start_webhook

    await self._start_webhook(

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_updater.py", line 685, in _start_webhook

    await self._bootstrap(

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_updater.py", line 852, in _bootstrap

    await self._network_loop_retry(

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_updater.py", line 769, in _network_loop_retry

    on_err_cb(telegram_exc)

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_updater.py", line 831, in bootstrap_on_err_cb

    raise exc

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_updater.py", line 755, in _network_loop_retry

    if not await do_action():

           ^^^^^^^^^^^^^^^^^

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_updater.py", line 734, in do_action

    return await action_cb()

           ^^^^^^^^^^^^^^^^^

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_updater.py", line 808, in bootstrap_set_webhook

    await self.bot.set_webhook(

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_extbot.py", line 3629, in set_webhook

    return await super().set_webhook(

           ^^^^^^^^^^^^^^^^^^^^^^^^^^

  File "/opt/venv/lib/python3.12/site-packages/telegram/_bot.py", line 4508, in set_webhook

    return await self._post(

           ^^^^^^^^^^^^^^^^^

  File "/opt/venv/lib/python3.12/site-packages/telegram/_bot.py", line 622, in _post

    return await self._do_post(

           ^^^^^^^^^^^^^^^^^^^^

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_extbot.py", line 375, in _do_post

    return await self.rate_limiter.process_request(

           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

 

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_aioratelimiter.py", line 245, in process_request

    return await self._run_request(

           ^^^^^^^^^^^^^^^^^^^^^^^^

  File "/opt/venv/lib/python3.12/site-packages/telegram/ext/_aioratelimiter.py", line 203, in _run_request

    return await callback(*args, **kwargs)

           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

  File "/opt/venv/lib/python3.12/site-packages/telegram/_bot.py", line 651, in _do_post

    result = await request.post(

             ^^^^^^^^^^^^^^^^^^^

  File "/opt/venv/lib/python3.12/site-packages/telegram/request/_baserequest.py", line 200, in post

    result = await self._request_wrapper(

             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

  File "/opt/venv/lib/python3.12/site-packages/telegram/request/_baserequest.py", line 381, in _request_wrapper

    raise BadRequest(message)

telegram.error.BadRequest: Bad webhook: an https url must be provided for webhook

2025-08-09 04:58:17,042 | INFO | root | Running webhook at 0.0.0.0:8080 path=/hook-1111 url=https://lead-counter-bot-production.up.railway.app/hook-1111

2025-08-09 04:58:17,492 | INFO | httpx | HTTP Request: POST https://api.telegram.org/bot8190019941:AAHkTZIJ1eE8nq2oQf0M0swTb6co73MRQMo/getMe "HTTP/1.1 200 OK"

2025-08-09 04:58:17,642 | INFO | httpx | HTTP Request: POST https://api.telegram.org/bot8190019941:AAHkTZIJ1eE8nq2oQf0M0swTb6co73MRQMo/setWebhook "HTTP/1.1 400 Bad Request"

2025-08-09 04:58:17,643 | ERROR | telegram.ext.Updater | Error while bootstrap set webhook: Bad webhook: an https url must be provided for webhook
