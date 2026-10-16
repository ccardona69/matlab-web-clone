%% Álgebra Lineal, Descomposición SVD y Resolución de Sistemas (mldivide)
M = magic(4)
det_M = det(M)
tr_M = trace(M)
rk_M = rank(M)

% Sistema lineal bien condicionado A * x = b resuelto con operador backslash (\)
A = [4 -1 1; -1 4.25 2.75; 1 2.75 3.5]
b = [4; 6; 7.25]
x = A \ b

% Verificación de residuo ||A*x - b||
residuo = norm(A * x - b)

% Descomposición en Valores Singulares (SVD) y Eigenvalores
[U, S, V] = svd(A);
autovalores = eig(A)
fprintf('Sistema resuelto con residuo L2 = %.3e\n', residuo);
