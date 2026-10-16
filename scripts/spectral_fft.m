%% Análisis Espectral FFT y Filtrado de Señales — MATLAB R2026b (REA Clone)
fs = 1000;
t = 0:0.001:1;
f1 = 50;
f2 = 120;

% Señal compuesta con dos armónicos + ruido gaussiano
signal = 0.7 * sin(2 * pi * f1 * t) + sin(2 * pi * f2 * t);
noisy = signal + 0.35 * randn(1, length(t));

% Transformada Rápida de Fourier (FFT)
N = length(t);
Y = fft(noisy);
P2 = abs(Y / N);
P1 = P2(1:500);
freqs = linspace(0, fs / 2, 500);

figure(1);
clf;
subplot(2, 1, 1);
plot(t(1:200), noisy(1:200), 'b-');
hold on;
plot(t(1:200), signal(1:200), 'r-');
title('Dominio del Tiempo: Señal Compuesta (50 Hz + 120 Hz)');
xlabel('Tiempo (s)');
ylabel('Amplitud (V)');
legend('Señal con ruido', 'Señal limpia');

subplot(2, 1, 2);
plot(freqs, P1, 'c-');
title('Espectro de Magnitud Unilateral |P1(f)|');
xlabel('Frecuencia (Hz)');
ylabel('|P1(f)|');

fprintf('Frecuencias dominantes procesadas sobre N = %d muestras.\n', N);
