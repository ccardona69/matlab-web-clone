% capture_catalogs.m - Captura cruda del catalogo de paridad (WO-04, WS-9):
% errores, warnings y formatos numericos, ejecutando el MATLAB real.
% Uso: matlab -batch capture_catalogs   (desde este directorio; stdout a
% docs/acceptance/golden-catalogs.txt por el runner).
% Los outputs capturados son datos de prueba (entradas -> salidas), sin
% contenido protegido de MathWorks. Gemini estructurara estos datos en
% docs/acceptance/catalogs/ y ampliara el set.

fprintf('<GOLDEN-CATALOGS MATLAB %s>\n', version);
fprintf('<PLATFORM %s>\n', computer);

cases = {
  'CT-01', 'undefined_fn_xyz';
  'CT-02', 'no_such_var_abc';
  'CT-03', 'a = [1 2 3]; a(5)';
  'CT-04', 'a = [1 2 3]; a(0)';
  'CT-05', 'a = [1 2 3]; a(''x'')';
  'CT-06', 'a = [1 2 3]; a(1.5)';
  'CT-07', 'sin()';
  'CT-08', 'sin(1, 2, 3)';
  'CT-09', 'zeros()';
  'CT-10', 'zeros(2.5)';
  'CT-11', 'zeros(-1)';
  'CT-12', '[1 2] + [1 2 3]';
  'CT-13', '[1 2; 3 4] * [1 2 3]';
  'CT-14', '[1 2] \ [1 2 3]';
  'CT-15', '[1 2; 3]';
  'CT-16', '[1 2 3';
  'CT-17', 'if true';
  'CT-18', '1var = 3';
  'CT-19', 'x = ;';
  'CT-20', 'sqrt(''abc'')';
  'CT-21', 'reshape(1:6, 4, 2)';
  'CT-22', 'inv([1 2 3; 4 5 6])';
  'CT-23', 'struct(''a'')';
  'CT-24', 'struct(1)';
  'CT-25', 's = struct(''a'', 1); s.z';
  'CT-26', 's = struct(''a'', 1); rmfield(s, ''z'')';
  'CT-27', 'fieldnames(5)';
  'CT-28', 'error(''boom'')';
  'CT-29', 'error(''MyApp:Test'', ''boom %d'', 42)';
  'CT-30', 'assert(false, ''fallo controlado'')';
  'CT-31', 'q = 1; q.b';
  'CT-32', 'num2str(pi, ''badfmt'')';
  'CT-33', 'cell(1.5)';
  'CT-34', 'length()';
  'CT-35', 'numel()';
  'CT-36', 'linspace(0, 1, -3)';
  'CT-37', 'eye(-2)';
  'CT-38', 'polyfit(1:3, 1:5, 2)';
  'CT-39', 'interp1([1 2 3], [1 2], 1.5)';
  'CT-40', 'strjoin(1)';
  'CT-41', 'regexp(123)';
  'CT-42', 'sol = ode45(@(t,y) -y, [0 1], [1 2; 3 4]); disp(''ode45 ok''); disp(size(sol.x)); disp(size(sol.y))';
  'CT-43', 'containers.Map()';
  'CT-44', 'd = dictionary(); d(1)';
  'CT-45', 'v = [1 2 3]; v(end + 5)';
  'CT-46', 'pkg_does_not_exist.fn(1)';
  'CT-47', 'run(''nonexistent_script_xyz.m'')';
  'CT-48', 'load(''nonexistent_mat_xyz.mat'')';
  'CT-49', 'delete(''nonexistent_file_xyz.txt'')';
  'CT-50', 'cd(''C:\definitely_not_exists_xyz'')';
  'CT-51', 'inv([1 2; 2 4])';
  'CT-52', 'A = [1 2; 2 4 + 1e-13]; A \ [1; 2]';
  'CT-53', 'x = int8(200)';
  'CT-54', 'x = uint8(-1)';
  'CT-55', 'x = int16(1e6)';
  'CT-56', 'strmatch(''a'', {''a'', ''b''})';
  'CT-57', 'x = 1:10; y = x; p = polyfit(x, y, 9)';
  'CT-58', 'warning(''texto de prueba'')';
  'CT-59', 'warning(''MyWarn:Test'', ''cuidado %d'', 7)';
  'CT-60', 'fzero(@(x) x.^2 + 1, 0)';
  'FM-01', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format short; disp(V)';
  'FM-02', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format long; disp(V)';
  'FM-03', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format shortE; disp(V)';
  'FM-04', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format longE; disp(V)';
  'FM-05', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format shortG; disp(V)';
  'FM-06', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format longG; disp(V)';
  'FM-07', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format shortEng; disp(V)';
  'FM-08', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format longEng; disp(V)';
  'FM-09', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format bank; disp(V)';
  'FM-10', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format hex; disp(V)';
  'FM-11', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format rat; disp(V)';
  'FM-12', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format +; disp(V)';
  'FM-13', 'V = [pi; 1234.5678; 1/3; 0.0000123456; 1e10; -1]; format compact; disp(V); disp(V'')';
};

for k = 1:size(cases, 1)
  id = cases{k, 1};
  code = cases{k, 2};
  fprintf('<CASE %s>\n', id);
  fprintf('<CODE %s>\n', code);
  format short;
  lastwarn('');
  try
    eval(code);
  catch err
    fprintf('<ERROR %s | %s>\n', err.identifier, err.message);
  end
  [warnMsg, warnId] = lastwarn;
  if ~isempty(warnMsg)
    fprintf('<WARN %s | %s>\n', warnId, warnMsg);
  end
  fprintf('<END %s>\n', id);
  clearvars -except cases k
end

fprintf('<EOG>\n');
