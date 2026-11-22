import { useAuthStore } from "../store/authStore";

export const attachInterceptors = (instance) => {
  // Request interceptor
  instance.interceptors.request.use((config) => {
    const token = useAuthStore.getState().access;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  });

  // Response interceptor
  instance.interceptors.response.use(
    (res) => res,
    async (err) => {
      const original = err.config;

      if (err.response?.status === 401 && !original._retry) {
        original._retry = true;

        const refresh = useAuthStore.getState().refresh;

        if (refresh) {
          try {
            const { data } = await instance.post(
              "/auth/token/refresh/",
              { refresh }
            );

            useAuthStore.getState().setAccess(data.access);

            original.headers.Authorization = `Bearer ${data.access}`;
            return instance(original);
          } catch {
            useAuthStore.getState().logout();
          }
        } else {
          useAuthStore.getState().logout();
        }
      }

      return Promise.reject(err);
    }
  );

  return instance;
};