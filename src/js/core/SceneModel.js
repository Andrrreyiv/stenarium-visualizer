// Состояние сцены: какая панель лежит в какой зоне. Ничего про DOM не знает.

export class SceneModel {
  constructor(scene) {
    this.zones = scene.zones.map((z) => z.id);
    // Стартовое состояние клиент задал явно: три одинаковых, вариант дерева.
    this.defaults = { ...scene.defaults };
    this.state = { ...scene.defaults };
    this.listeners = [];
  }

  onChange(fn) { this.listeners.push(fn); }

  emit(zone) { this.listeners.forEach((fn) => fn(this.state, zone)); }

  get(zone) { return this.state[zone]; }

  set(zone, code) {
    if (!this.zones.includes(zone)) return false;
    if (this.state[zone] === code) return false;
    this.state[zone] = code;
    this.emit(zone);
    return true;
  }

  // Сброс возвращает именно стартовое состояние, а не пустую стену рендера.
  reset() {
    this.state = { ...this.defaults };
    this.emit(null);
  }

  isDefault() {
    return this.zones.every((z) => this.state[z] === this.defaults[z]);
  }
}
