% capture_catalogs_extra.m - Captura de warnings/errores adicionales (WO-04, WS-9):
% extensión para completar cobertura de warnings (meta >= 15), ejecutando el MATLAB real.
% Uso: matlab -batch capture_catalogs_extra  (desde este directorio; stdout a
% docs/acceptance/golden-catalogs-extra.txt por el runner).
% Los outputs capturados son datos de prueba (entradas -> salidas), sin
% contenido protegido de MathWorks.

fprintf('<GOLDEN-CATALOGS-EXTRA MATLAB %s>\n', version);
fprintf('<PLATFORM %s>\n', computer);

cases = {
  'CT-61', 'polyfit(1:3, [1 2 3], 3)';
  'CT-62', 'A = [1 2; 2 4]; A \ [1; 2]';
  'CT-63', 'inv(hilb(15))';
  'CT-64', 'nchoosek(100, 50)';
  'CT-65', 'rmpath(''C:\no_such_dir_xyz'')';
  'CT-66', 'table([1;2], [3;4], ''VariableNames'', {''a'',''a''})';
  'CT-67', '1:0:5';
  'CT-68', '[1, 2+3i] < 2';
  'CT-69', 'strmatch(''a'', {''a'',''b''})';
  'CT-70', 'strread(''1 2'', ''%d'')';
  'CT-71', 'ode45(@(t,y) y.^2, [0 10], 1)';
  'CT-72', 'quad(@(x) x.^2, 0, 1)';
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
