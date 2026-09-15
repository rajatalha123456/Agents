import client from "./client";

export const register = (data) => client.post("/auth/register/", data);
export const login = (data) => client.post("/auth/login/", data);
export const fetchMe = () => client.get("/auth/me/");

export const fetchCashPosition = () => client.get("/cash-flows/position/");
export const updateCashPosition = (data) => client.patch("/cash-flows/position/", data);

export const fetchAssets = () => client.get("/assets/");
export const createAsset = (data) => client.post("/assets/", data);
export const updateAsset = (id, data) => client.patch(`/assets/${id}/`, data);
export const deleteAsset = (id) => client.delete(`/assets/${id}/`);

export const fetchCashFlowItems = (kind) =>
  client.get("/cash-flows/items/", { params: kind ? { kind } : {} });
export const createCashFlowItem = (data) => client.post("/cash-flows/items/", data);
export const updateCashFlowItem = (id, data) => client.patch(`/cash-flows/items/${id}/`, data);
export const deleteCashFlowItem = (id) => client.delete(`/cash-flows/items/${id}/`);

export const fetchForecast = (horizon, scenario) =>
  client.get("/forecast/", { params: { horizon, scenario } });
export const fetchForecastCompare = (horizon) =>
  client.get("/forecast/compare/", { params: { horizon } });
export const fetchDashboardSummary = () => client.get("/dashboard/summary/");

export const sendChatMessage = (data) => client.post("/ai/chat/", data);
export const runWhatIf = (data) => client.post("/ai/whatif/", data);
