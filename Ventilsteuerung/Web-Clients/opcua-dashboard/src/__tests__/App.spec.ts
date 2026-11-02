import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import App from '../App.vue'

describe('App', () => {
  it('renders disconnected with all controls disabled', () => {
    const wrapper = mount(App)
    expect(wrapper.find('h1').text()).toContain('H300')
    expect(wrapper.find('.status-line').text()).toBe('Getrennt')
    const steuerung = wrapper.findAll('.bedienung button')
    expect(steuerung.length).toBeGreaterThan(0)
    for (const b of steuerung) expect(b.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})
