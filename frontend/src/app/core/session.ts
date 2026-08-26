import { Service, signal } from '@angular/core';

const NAME_KEY = 'abl.session.name';
const ROLE_KEY = 'abl.session.role';

@Service()
export class Session {
  readonly name = signal<string>(localStorage.getItem(NAME_KEY) ?? 'Alex Chen');
  readonly role = signal<string>(localStorage.getItem(ROLE_KEY) ?? 'Credit Officer');

  setName(value: string): void {
    this.name.set(value);
    localStorage.setItem(NAME_KEY, value);
  }

  setRole(value: string): void {
    this.role.set(value);
    localStorage.setItem(ROLE_KEY, value);
  }
}
