% capture_golden.m - Captura las salidas doradas del set de aceptacion ejecutando
% el MATLAB real (licencia activa del usuario). Uso:
%   matlab -batch capture_golden
% ejecutado desde este directorio; stdout se redirige a
% docs/acceptance/golden-output.txt por el runner.
% Los outputs capturados son datos de prueba (entradas -> salidas), sin contenido
% protegido de MathWorks.

fprintf('<GOLDEN MATLAB %s>\n', version);
fprintf('<PLATFORM %s>\n', computer);

cases = {
  'AC-01', 'pi';
  'AC-02', 'format long; pi';
  'AC-03', 'A = [1 2 3; 4 5 6; 7 8 10]; disp(A)';
  'AC-04', 'disp([1 2 3; 4 5 6; 7 8 10]'');';
  'AC-05', 'magic(4)';
  'AC-06', 'sum(1:100)';
  'AC-07', 'x = linspace(0, 2*pi, 5); disp(x)';
  'AC-08', 'sqrt(-4)';
  'AC-09', '1/0';
  'AC-10', '0/0';
  'AC-11', 'sprintf(''%.3f'', pi)';
  'AC-12', 'num2str(pi, ''%.5e'')';
  'AC-13', 'strcat(''ma'', ''tlab'')';
  'AC-14', 'sin(1, 2, 3)';
  'AC-15', 'undefined_fn_xyz(1)';
  'AC-16', 'inv([1 2; 2 4])';
  'AC-17', 'eig([2 0; 0 3])';
  'AC-18', 'format rat; pi';
  'AC-19', 'struct(''a'', 1)';
  'AC-20', 'q = 42; whos q';
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
