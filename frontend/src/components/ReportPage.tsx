import { useEffect, useState } from 'react';

type CurrentUser = {
  username: string;
  customerId: number;
};

const apiUrl = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const formatDate = (date: Date) => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const initialPeriod = () => {
  const end = new Date();
  end.setDate(end.getDate() - 1);
  const start = new Date(end);
  start.setDate(start.getDate() - 6);
  return { start: formatDate(start), end: formatDate(end) };
};

const ReportPage: React.FC = () => {
  const period = initialPeriod();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [initializing, setInitializing] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState(period.start);
  const [endDate, setEndDate] = useState(period.end);

  useEffect(() => {
    fetch(`${apiUrl}/auth/me`, { credentials: 'include' })
      .then(async (response) => {
        if (response.status === 401) return null;
        if (!response.ok) throw new Error('Не удалось проверить сессию');
        return response.json() as Promise<CurrentUser>;
      })
      .then(setUser)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setInitializing(false));
  }, []);

  const login = () => {
    window.location.assign(`${apiUrl}/auth/login`);
  };

  const logout = async () => {
    await fetch(`${apiUrl}/auth/logout`, {
      method: 'POST',
      credentials: 'include',
    });
    setUser(null);
  };

  const downloadReport = async () => {
    try {
      setLoading(true);
      setError(null);
      const query = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
        format: 'csv',
      });
      const response = await fetch(`${apiUrl}/reports?${query}`, {
        credentials: 'include',
      });
      if (response.status === 401) {
        setUser(null);
        throw new Error('Сессия истекла. Войдите снова.');
      }
      if (response.status === 409) {
        throw new Error('Airflow ещё не обработал весь выбранный период.');
      }
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || 'Не удалось сформировать отчёт');
      }

      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = objectUrl;
      anchor.download = `bionicpro-report-${startDate}-${endDate}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Произошла ошибка');
    } finally {
      setLoading(false);
    }
  };

  if (initializing) {
    return <main className="screen"><p className="status">Проверяем сессию…</p></main>;
  }

  if (!user) {
    return (
      <main className="screen">
        <section className="card login-card">
          <span className="eyebrow">BionicPRO</span>
          <h1>Отчёты по работе протеза</h1>
          <p>Авторизуйтесь, чтобы скачать отчёт только по своим устройствам.</p>
          <button className="primary" onClick={login}>Войти через SSO</button>
          {error && <p className="error" role="alert">{error}</p>}
        </section>
      </main>
    );
  }

  return (
    <main className="screen">
      <section className="card report-card">
        <header>
          <div>
            <span className="eyebrow">BionicPRO · пилот #{user.customerId}</span>
            <h1>Отчёт по работе протеза</h1>
            <p>Пользователь: {user.username}</p>
          </div>
          <button className="secondary" onClick={logout}>Выйти</button>
        </header>

        <div className="period">
          <label>
            Начало периода
            <input
              type="date"
              value={startDate}
              max={endDate}
              onChange={(event) => setStartDate(event.target.value)}
            />
          </label>
          <label>
            Конец периода
            <input
              type="date"
              value={endDate}
              min={startDate}
              onChange={(event) => setEndDate(event.target.value)}
            />
          </label>
        </div>

        <button className="primary" onClick={downloadReport} disabled={loading}>
          {loading ? 'Готовим отчёт…' : 'Скачать CSV-отчёт'}
        </button>
        <p className="hint">Можно запросить не более 31 дня, уже обработанного Airflow.</p>
        {error && <p className="error" role="alert">{error}</p>}
      </section>
    </main>
  );
};

export default ReportPage;
