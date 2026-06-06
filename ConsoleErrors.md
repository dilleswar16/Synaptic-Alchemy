Git connection issue:
Corvin API error 409: GitHub repository 'MetLife-Global/14470_chad' was not found or is not accessible with the configured token. Verify repo URL and PAT permissions (Issues: read/write, repository access).
INFO:     127.0.0.1:63151 - "POST /investigations/fd24e1fd-bb14-4dc9-9eeb-48e1f1cca056/create-github-issue HTTP/1.1" 409 Conflict



Corvin API error 502: GitHub API returned 422: {"message":"Validation Failed","errors":[{"value":["ChAD Agency"],"resource":"Issue","field":"assignees","code":"invalid"}],"documentation_url":"https://docs.github.com/rest/issues/issues#create-an-issue","status":"422"}



ERROR:    Exception in ASGI application
Traceback (most recent call last):
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\engine\base.py", line 1967, in _exec_single_context
    self.dialect.do_execute(
    ~~~~~~~~~~~~~~~~~~~~~~~^
        cursor, str_statement, effective_parameters, context
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\engine\default.py", line 952, in do_execute
    cursor.execute(statement, parameters)
    ~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^
sqlite3.OperationalError: no such column: application_services.git_copilot_agent

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\uvicorn\protocols\http\httptools_impl.py", line 420, in run_asgi
    result = await app(  # type: ignore[func-returns-value]
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        self.scope, self.receive, self.send
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\uvicorn\middleware\proxy_headers.py", line 60, in __call__
    return await self.app(scope, receive, send)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\fastapi\applications.py", line 1163, in __call__
    await super().__call__(scope, receive, send)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\applications.py", line 90, in __call__
    await self.middleware_stack(scope, receive, send)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\middleware\errors.py", line 186, in __call__
    raise exc
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\middleware\errors.py", line 164, in __call__
    await self.app(scope, receive, _send)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\middleware\cors.py", line 96, in __call__
    await self.simple_response(scope, receive, send, request_headers=headers)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\middleware\cors.py", line 154, in simple_response
    await self.app(scope, receive, send)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\middleware\exceptions.py", line 63, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\fastapi\middleware\asyncexitstack.py", line 18, in __call__
    await self.app(scope, receive, send)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\routing.py", line 660, in __call__
    await self.middleware_stack(scope, receive, send)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\routing.py", line 680, in app
    await route.handle(scope, receive, send)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\routing.py", line 276, in handle
    await self.app(scope, receive, send)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\fastapi\routing.py", line 134, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\fastapi\routing.py", line 120, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\fastapi\routing.py", line 674, in app
    raw_response = await run_endpoint_function(
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    ...<3 lines>...
    )
    ^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\fastapi\routing.py", line 330, in run_endpoint_function
    return await run_in_threadpool(dependant.call, **values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\starlette\concurrency.py", line 32, in run_in_threadpool
    return await anyio.to_thread.run_sync(func)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\anyio\to_thread.py", line 63, in run_sync
    return await get_async_backend().run_sync_in_worker_thread(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
        func, args, abandon_on_cancel=abandon_on_cancel, limiter=limiter
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\anyio\_backends\_asyncio.py", line 2518, in run_sync_in_worker_thread
    return await future
           ^^^^^^^^^^^^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\anyio\_backends\_asyncio.py", line 1002, in run
    result = context.run(func, *args)
  File "C:\Users\nigamn\Documents\AUAzDoRepos\Corvin\Synaptic Alchemy\apps\api\routes\investigations.py", line 2019, in create_github_issue
    .all()
     ~~~^^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\orm\query.py", line 2711, in all
    return self._iter().all()  # type: ignore
           ~~~~~~~~~~^^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\orm\query.py", line 2864, in _iter
    result: Union[ScalarResult[_T], Result[_T]] = self.session.execute(
                                                  ~~~~~~~~~~~~~~~~~~~~^
        statement,
        ^^^^^^^^^^
        params,
        ^^^^^^^
        execution_options={"_sa_orm_load_options": self.load_options},
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\orm\session.py", line 2351, in execute
    return self._execute_internal(
           ~~~~~~~~~~~~~~~~~~~~~~^
        statement,
        ^^^^^^^^^^
    ...<4 lines>...
        _add_event=_add_event,
        ^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\orm\session.py", line 2249, in _execute_internal
    result: Result[Any] = compile_state_cls.orm_execute_statement(
                          ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^
        self,
        ^^^^^
    ...<4 lines>...
        conn,
        ^^^^^
    )
    ^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\orm\context.py", line 306, in orm_execute_statement
    result = conn.execute(
        statement, params or {}, execution_options=execution_options
    )
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\engine\base.py", line 1419, in execute
    return meth(
        self,
        distilled_parameters,
        execution_options or NO_OPTIONS,
    )
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\sql\elements.py", line 527, in _execute_on_connection
    return connection._execute_clauseelement(
           ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~^
        self, distilled_params, execution_options
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\engine\base.py", line 1641, in _execute_clauseelement
    ret = self._execute_context(
        dialect,
    ...<8 lines>...
        cache_hit=cache_hit,
    )
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\engine\base.py", line 1846, in _execute_context
    return self._exec_single_context(
           ~~~~~~~~~~~~~~~~~~~~~~~~~^
        dialect, context, statement, parameters
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\engine\base.py", line 1986, in _exec_single_context
    self._handle_dbapi_exception(
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~^
        e, str_statement, effective_parameters, cursor, context
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\engine\base.py", line 2363, in _handle_dbapi_exception
    raise sqlalchemy_exception.with_traceback(exc_info[2]) from e
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\engine\base.py", line 1967, in _exec_single_context
    self.dialect.do_execute(
    ~~~~~~~~~~~~~~~~~~~~~~~^
        cursor, str_statement, effective_parameters, context
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    )
    ^
  File "c:\Users\nigamn\Documents\AUAzDoRepos\Corvin\.venv\Lib\site-packages\sqlalchemy\engine\default.py", line 952, in do_execute
    cursor.execute(statement, parameters)
    ~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^
sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) no such column: application_services.git_copilot_agent
[SQL: SELECT application_services.id AS application_services_id, application_services.application_id AS application_services_application_id, application_services.service_name AS application_services_service_name, application_services.display_name AS application_services_display_name, application_services.namespace AS application_services_namespace, application_services.tier AS application_services_tier, application_services.dependencies AS application_services_dependencies, application_services.metadata_json AS application_services_metadata_json, application_services.k8s_app_label AS application_services_k8s_app_label, application_services.git_provider AS application_services_git_provider, application_services.git_repo_url AS application_services_git_repo_url, application_services.git_branch AS application_services_git_branch, application_services.git_token_encrypted AS application_services_git_token_encrypted, application_services.git_assignee AS application_services_git_assignee, application_services.git_copilot_agent AS application_services_git_copilot_agent 
FROM application_services 
WHERE application_services.service_name = ? ORDER BY application_services.id DESC]
[parameters: ('partnerapis',)]
(Background on this error at: https://sqlalche.me/e/20/e3q8)